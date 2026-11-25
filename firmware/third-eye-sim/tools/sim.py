"""Test harness for the Third Eye QEMU build.

Starts Espressif QEMU (esp32s3, 8 MB octal PSRAM, emulated SD card, OpenCores
Ethernet) and plays three roles over TCP:
  bench - the simulated hardware the emulator lacks (buttons, temperature,
          battery) and the firmware's test reports
  ble   - the phone's BLE link (commands, audio stream, prompts, key-phrase saves)
  wifi  - the phone's Wi-Fi clip receiver
"""
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import threading
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
QEMU = os.environ.get("TE_QEMU", shutil.which("qemu-system-xtensa") or "qemu-system-xtensa")

MSG = dict(HELLO=0x01, STATUS=0x02, AUDIO=0x03, EVENT=0x04, PROMPT_BEGIN=0x05, PROMPT_AUDIO=0x06,
           PROMPT_FRAME=0x07, PROMPT_END=0x08, CLIP_QUEUED=0x09, CLIP_DELETED=0x0A, APPROVAL=0x0B,
           CLIP_BEGIN=0x41, FILE_HDR=0x42, DATA=0x43, CLIP_END=0x44,
           PING=0x81, CMD=0x82, REPLY=0x83, ACK=0x84)
NAME = {v: k for k, v in MSG.items()}

# ---------------------------------------------------------------- speed models
GOOD_CARD = dict(sd_write_Bps=1600000, sd_read_Bps=2000000, sd_pause_every_kb=2048,
                 sd_pause_min_ms=40, sd_pause_max_ms=250, sd_long_every_mb=200,
                 sd_long_min_ms=400, sd_long_max_ms=800)
CHEAP_CARD = dict(sd_write_Bps=530000, sd_read_Bps=670000, sd_pause_every_kb=1024,
                  sd_pause_min_ms=80, sd_pause_max_ms=500, sd_long_every_mb=100,
                  sd_long_min_ms=800, sd_long_max_ms=1600)
BLE_SLOW = dict(ble_Bps=50000)
BLE_FAST = dict(ble_Bps=100000)


# ---------------------------------------------------------------- ADPCM decoder
STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
        73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408,
        449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
        2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
        9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
IDX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]


def adpcm_decode(block):
    pred = struct.unpack_from("<h", block, 0)[0]
    index = block[2]
    out = []
    for b in block[4:]:
        for code in (b & 15, b >> 4):
            step = STEP[index]
            d = step >> 3
            if code & 4: d += step
            if code & 2: d += step >> 1
            if code & 1: d += step >> 2
            pred = max(-32768, min(32767, pred - d if code & 8 else pred + d))
            index = max(0, min(88, index + IDX[code]))
            out.append(pred)
    return out


def goertzel_ratio(x, f, fs=16000):
    """Share of signal power at frequency f (0..1)."""
    import math
    n = len(x)
    k = round(n * f / fs)
    w = 2 * math.pi * k / n
    c = 2 * math.cos(w)
    s1 = s2 = 0.0
    for v in x:
        s0 = v + c * s1 - s2
        s2, s1 = s1, s0
    p = s1 * s1 + s2 * s2 - c * s1 * s2
    tot = sum(v * v for v in x) * n / 2
    return p / tot if tot else 0.0


# ---------------------------------------------------------------- clip checks
def parse_mjp(data):
    """Returns (frames, seqs, bad) for a chunk file of TEF1 records."""
    seqs, bad, o = [], 0, 0
    while o + 16 <= len(data):
        magic, seq, ts, ln = struct.unpack_from("<IIII", data, o)
        if magic != 0x31464554:
            bad += 1
            break
        j = data[o + 16:o + 16 + ln]
        if len(j) != ln or j[:2] != b"\xff\xd8" or j[-2:] != b"\xff\xd9":
            bad += 1
        seqs.append(seq)
        o += 16 + ln
    return seqs, bad


def check_clip(files):
    seqs, bad = [], 0
    for name in sorted(n for n in files if n.lower().endswith(".mjp")):
        s, b = parse_mjp(files[name])
        seqs += s
        bad += b
    gaps = sum(max(0, b - a - 1) for a, b in zip(seqs, seqs[1:]))
    wav = next((files[n] for n in files if n.lower().endswith(".wav")), b"")
    audio_s = 0.0
    if len(wav) >= 44 and wav[:4] == b"RIFF":
        ch, rate = struct.unpack_from("<HI", wav, 22)
        audio_s = (len(wav) - 44) / (rate * ch * 2)
    meta = next((files[n].decode(errors="replace") for n in files if n.lower() == "meta.txt"), "")
    return dict(frames=len(seqs), seq_gaps=gaps, bad_frames=bad, audio_s=round(audio_s, 2),
                video_files=sum(1 for n in files if n.lower().endswith(".mjp")),
                video_s=round((len(seqs)) / 15.0, 2), meta=dict(l.split("=", 1) for l in meta.splitlines() if "=" in l))


# ---------------------------------------------------------------- framing
def frame(t, payload=b""):
    if isinstance(payload, str):
        payload = payload.encode()
    n = len(payload)
    return bytes([t, n & 255, (n >> 8) & 255, (n >> 16) & 255]) + payload


class FrameReader:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf += data
        out = []
        while len(self.buf) >= 4:
            n = self.buf[1] | (self.buf[2] << 8) | (self.buf[3] << 16)
            if len(self.buf) < 4 + n:
                break
            out.append((self.buf[0], bytes(self.buf[4:4 + n])))
            del self.buf[:4 + n]
        return out


def listener(port=0):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(4)
    return s, s.getsockname()[1]


# ---------------------------------------------------------------- the mock phone + bench
class Phone:
    def __init__(self, log_path=None):
        self.lock = threading.Condition()
        self.lines = []          # (host_time, fw_ms, text)
        self.stats = []          # parsed STATS dicts with fw time
        self.msgs = []           # (host_time, type name, payload) from BLE
        self.audio = dict(pkts=0, bytes=0, gaps=0, last_seq=None, samples=[], times=[])
        self.clips = {}          # id -> check_clip result
        self.transfers = []      # dicts
        self.prompts = []
        self.approvals = []
        self.ble_connects = 0
        self.wifi_connects = 0
        self.away = False
        self.reply_mode = "ok"   # ok | approval | fail | none
        self.reply_pcm_samples = 8000
        self.wifi_plan = []      # list of modes for the next transfers: refuse | drop_mid | nack | noack
        self.ble_conn = None
        self.log = open(log_path, "w") if log_path else None
        self.stop = False
        self.bench_conn = None
        self.socks = {}
        for k in ("bench", "ble", "wifi"):
            s, p = listener()
            self.socks[k] = (s, p)
        self.ports = {k: v[1] for k, v in self.socks.items()}
        for k, fn in (("bench", self._bench), ("ble", self._ble), ("wifi", self._wifi)):
            threading.Thread(target=self._accept_loop, args=(k, fn), daemon=True).start()
        threading.Thread(target=self._pinger, daemon=True).start()

    # ---- logging and waiting
    def _log(self, s):
        if self.log:
            self.log.write("%.3f %s\n" % (time.time(), s))
            self.log.flush()

    def _accept_loop(self, k, fn):
        s = self.socks[k][0]
        while not self.stop and self.socks[k][0] is s:
            try:
                c, _ = s.accept()
            except OSError:
                return
            c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=fn, args=(c,), daemon=True).start()

    def wait_line(self, pattern, timeout=60, start=0):
        """Waits for a bench line matching regex; returns (index, match) or (None, None)."""
        rx = re.compile(pattern)
        end = time.time() + timeout
        i = start
        with self.lock:
            while True:
                while i < len(self.lines):
                    m = rx.search(self.lines[i][2])
                    if m:
                        return i, m
                    i += 1
                left = end - time.time()
                if left <= 0:
                    return None, None
                self.lock.wait(min(left, 0.5))

    def find_lines(self, pattern, start=0):
        rx = re.compile(pattern)
        with self.lock:
            return [(i, l) for i, l in enumerate(self.lines) if i >= start and rx.search(l[2])]

    def mark(self):
        with self.lock:
            return len(self.lines)

    def fw_ms(self):
        with self.lock:
            return self.lines[-1][1] if self.lines else 0

    # ---- bench
    def _bench(self, c):
        self.bench_conn = c
        f = c.makefile("r", encoding="utf-8", errors="replace")
        for line in f:
            line = line.rstrip("\n")
            fw = 0
            m = re.match(r"@(\d+) (.*)", line)
            if m:
                fw, line = int(m.group(1)), m.group(2)
            self._log("BENCH " + line)
            with self.lock:
                self.lines.append((time.time(), fw, line))
                if line.startswith("STATS "):
                    try:
                        d = json.loads(line[6:])
                        d["t_ms"] = fw
                        self.stats.append(d)
                    except ValueError:
                        pass
                self.lock.notify_all()

    def bench(self, cmd):
        for _ in range(100):
            if self.bench_conn:
                break
            time.sleep(0.1)
        self._log("TO_BENCH " + cmd)
        self.bench_conn.sendall((cmd + "\n").encode())

    def tap(self, btn="SB"):
        self.bench("BTN %s tap" % btn)

    def hold(self, btn="SB", ms=2000):
        self.bench("BTN %s hold %d" % (btn, ms))

    # ---- BLE
    def _pinger(self):
        while not self.stop:
            c = self.ble_conn
            if c and not self.away:
                try:
                    c.sendall(frame(MSG["PING"]))
                except OSError:
                    pass
            time.sleep(1.0)

    def send_cmd(self, **kw):
        c = self.ble_conn
        if not c:
            return False
        c.sendall(frame(MSG["CMD"], json.dumps(kw)))
        self._log("TO_BLE CMD " + json.dumps(kw))
        return True

    def go_away(self):
        """Phone out of range: drop BLE and refuse reconnects (Wi-Fi too)."""
        self.away = True
        for k in ("ble", "wifi"):      # out of range: connection attempts now fail
            ls = self.socks[k][0]
            try:
                ls.shutdown(socket.SHUT_RDWR)   # wakes the accept() thread
            except OSError:
                pass
            ls.close()
        c, self.ble_conn = self.ble_conn, None
        if c:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            c.close()
        self._log("PHONE away")

    def come_back(self):
        self.away = False
        for k, fn in (("ble", self._ble), ("wifi", self._wifi)):
            s, p = listener(self.ports[k])
            self.socks[k] = (s, p)
            threading.Thread(target=self._accept_loop, args=(k, fn), daemon=True).start()
        self._log("PHONE back")

    def _ble(self, c):
        if self.away:
            c.close()
            return
        self.ble_connects += 1
        self.ble_conn = c
        fr = FrameReader()
        prompt = {}
        while True:
            try:
                d = c.recv(65536)
            except OSError:
                d = b""
            if not d:
                break
            for t, p in fr.feed(d):
                name = NAME.get(t, hex(t))
                now = time.time()
                if t == MSG["AUDIO"]:
                    seq = struct.unpack_from("<I", p, 0)[0]
                    a = self.audio
                    if a["last_seq"] is not None and seq != a["last_seq"] + 1:
                        a["gaps"] += 1
                    a["last_seq"] = seq
                    a["pkts"] += 1
                    a["bytes"] += len(p) + 4
                    a["times"].append(now)
                    a["samples"] = (a["samples"] + adpcm_decode(p[4:]))[-16000:]
                    continue
                self._log("BLE %s %s" % (name, p[:200]))
                with self.lock:
                    self.msgs.append((now, name, p))
                    self.lock.notify_all()
                if t == MSG["PROMPT_BEGIN"]:
                    prompt = dict(begin=json.loads(p), t0=now)
                elif t == MSG["PROMPT_AUDIO"]:
                    prompt["audio_bytes"] = len(p)
                    prompt["audio_440"] = goertzel_ratio(adpcm_decode(p)[-8000:], 440) if len(p) > 100 else 0
                elif t == MSG["PROMPT_FRAME"]:
                    prompt["frame_bytes"] = len(p)
                    prompt["frame_ok"] = p[:2] == b"\xff\xd8" and p[-2:] == b"\xff\xd9"
                elif t == MSG["PROMPT_END"]:
                    prompt["t1"] = now
                    self.prompts.append(prompt)
                    threading.Thread(target=self._reply, args=(c, prompt["begin"]["id"]), daemon=True).start()
                elif t == MSG["APPROVAL"]:
                    self.approvals.append(json.loads(p))
        if self.ble_conn is c:
            self.ble_conn = None

    def _reply(self, c, pid):
        time.sleep(1.0)  # phone + LLM thinking time
        mode = self.reply_mode
        if mode == "none":
            return
        ok = mode != "fail"
        hdr = json.dumps(dict(id=pid, ok=ok, approval=(mode == "approval")))
        pcm = b"\x00\x10" * self.reply_pcm_samples if ok else b""
        try:
            c.sendall(frame(MSG["REPLY"], hdr.encode() + b"\n" + pcm))
        except OSError:
            pass

    # ---- Wi-Fi
    def _wifi(self, c):
        mode = self.wifi_plan.pop(0) if self.wifi_plan else "ok"
        if self.away or mode == "refuse":
            self._log("WIFI refused (%s)" % ("away" if self.away else mode))
            self.transfers.append(dict(result="refused"))
            c.close()
            return
        self.wifi_connects += 1
        fr = FrameReader()
        files, cur, clip, got = {}, None, None, 0
        t0 = time.time()
        while True:
            try:
                d = c.recv(65536)
            except OSError:
                d = b""
            if not d:
                if clip:
                    self.transfers.append(dict(id=clip["id"], result="link_lost", bytes=got))
                break
            got += len(d)
            if mode == "drop_mid" and got > 2_000_000:
                self._log("WIFI dropping mid-transfer")
                self.transfers.append(dict(id=clip["id"] if clip else None, result="dropped_by_phone", bytes=got))
                c.close()
                return
            for t, p in fr.feed(d):
                if t == MSG["CLIP_BEGIN"]:
                    clip = json.loads(p)
                    files, crc, t0, got = {}, 0, time.time(), len(d)
                elif t == MSG["FILE_HDR"]:
                    h = json.loads(p)
                    cur = h["name"]
                    files[cur] = bytearray()
                elif t == MSG["DATA"]:
                    files[cur] += p
                    crc = zlib.crc32(p, crc)
                elif t == MSG["CLIP_END"]:
                    end = json.loads(p)
                    dt = time.time() - t0
                    crc_ok = (end["crc"] & 0xffffffff) == (crc & 0xffffffff)
                    size_ok = sum(len(v) for v in files.values()) == clip["bytes"]
                    res = check_clip({k: bytes(v) for k, v in files.items()})
                    res.update(crc_ok=crc_ok, size_ok=size_ok, bytes=clip["bytes"], seconds=round(dt, 1))
                    ok = crc_ok and size_ok
                    if mode == "nack":
                        ok, res["forced"] = False, "nack"
                    tr = dict(id=clip["id"], result="ok" if ok else "nack", **res)
                    self.transfers.append(tr)
                    self._log("WIFI clip %s %s" % (clip["id"], json.dumps({k: v for k, v in tr.items() if k != "meta"})))
                    if ok:
                        self.clips[clip["id"]] = res
                    if mode != "noack":
                        c.sendall(frame(MSG["ACK"], json.dumps(dict(id=clip["id"], ok=ok))))
                    clip = None
        c.close()

    def close(self):
        self.stop = True
        for s, _ in self.socks.values():
            s.close()
        if self.log:
            self.log.close()


# ---------------------------------------------------------------- QEMU
class Emulator:
    def __init__(self, build_dir, workdir, cfg, sd_mb=1024, icount=None):
        self.build_dir, self.workdir, self.cfg, self.sd_mb, self.icount = build_dir, workdir, cfg, sd_mb, icount
        os.makedirs(workdir, exist_ok=True)
        self.proc = None

    def _flash(self):
        out = os.path.join(self.workdir, "flash.bin")
        subprocess.run(["python", "-m", "esptool", "--chip", "esp32s3", "merge_bin", "-o", out,
                        "--fill-flash-size", "8MB", "@flash_args"], cwd=self.build_dir, check=True,
                       stdout=subprocess.DEVNULL)
        text = "".join("%s=%s\n" % kv for kv in self.cfg.items()).encode() + b"\0"
        with open(out, "r+b") as f:
            f.seek(0x310000)
            f.write(text)
        eff = os.path.join(self.workdir, "efuse.bin")
        e = bytearray(1024)
        e[38] = 0x0C   # chip revision v0.3, as idf.py qemu does
        open(eff, "wb").write(e)
        sd = os.path.join(self.workdir, "sd.img")
        if os.path.exists(sd):
            os.remove(sd)
        if self.sd_mb:
            with open(sd, "wb") as f:
                f.truncate(self.sd_mb * 1024 * 1024)
        return out, eff, sd

    def start(self):
        flash, eff, sd = self._flash()
        args = [QEMU, "-M", "esp32s3", "-m", "8M",
                "-drive", "file=%s,if=mtd,format=raw" % flash,
                "-drive", "file=%s,if=none,format=raw,id=efuse" % eff,
                "-global", "driver=nvram.esp.efuse,property=drive,value=efuse",
                "-global", "driver=timer.esp32s3.timg,property=wdt_disable,value=true",
                "-global", "driver=ssi_psram,property=is_octal,value=true",
                "-nic", "user,model=open_eth",
                "-nographic", "-serial", "file:%s" % os.path.join(self.workdir, "serial.log"),
                "-monitor", "none"]
        if self.sd_mb:   # sd_mb=0: no card in the slot
            args += ["-drive", "file=%s,if=sd,format=raw" % sd]
        if self.icount is not None:
            args += ["-icount", "shift=%d,sleep=on" % self.icount]
        self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=open(os.path.join(self.workdir, "qemu.err"), "w"))

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def boot(build_dir, workdir, extra_cfg=None, sd_mb=1024, icount=None, seed=1):
    """Starts a phone + emulator pair. Returns (phone, emulator) once the firmware is READY."""
    phone = Phone(os.path.join(workdir, "phone.log") if os.makedirs(workdir, exist_ok=True) is None else None)
    cfg = dict(host_ip="10.0.2.2", bench_port=phone.ports["bench"], ble_port=phone.ports["ble"],
               wifi_port=phone.ports["wifi"], seed=seed)
    cfg.update(GOOD_CARD)
    cfg.update(extra_cfg or {})
    emu = Emulator(build_dir, workdir, cfg, sd_mb=sd_mb, icount=icount)
    emu.start()
    i, _ = phone.wait_line(r"^READY", timeout=120)
    if i is None:
        emu.stop()
        phone.close()
        raise RuntimeError("firmware did not boot; see %s/serial.log" % workdir)
    return phone, emu
