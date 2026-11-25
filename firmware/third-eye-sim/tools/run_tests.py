#!/usr/bin/env python3
"""Automated feature and error-path tests for the Third Eye firmware in QEMU.

Each test boots a fresh emulator with a blank 1 GB SD card image, drives the
buttons/sensors through the bench socket and the phone side through the BLE
and Wi-Fi sockets, then checks what happened.

  python tools/run_tests.py --build /tmp/te-sim [--only name1,name2] [-j 2]
"""
import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402


class T:
    def __init__(self, name):
        self.name, self.checks, self.metrics = name, [], {}

    def check(self, desc, ok, detail=""):
        self.checks.append(dict(check=desc, ok=bool(ok), detail=str(detail)))
        return ok

    @property
    def passed(self):
        return all(c["ok"] for c in self.checks) and bool(self.checks)


def wait(ph, pat, timeout=60, start=0):
    i, m = ph.wait_line(pat, timeout, start)
    return m


def stats(ph):
    return ph.stats[-1] if ph.stats else {}


def fresh_stats(ph, timeout=10):
    n = len(ph.stats)
    end = time.time() + timeout
    while time.time() < end and len(ph.stats) == n:
        time.sleep(0.2)
    return stats(ph)


def start_listen(ph, t):
    m = ph.mark()
    ph.tap("SB")
    t.check("short press in Sleep starts Listen", wait(ph, r"^STATE listen", 20, m))
    return m


def strip(tr):
    return {k: v for k, v in tr.items() if k != "meta"}


def clip_ok(t, tr, what, min_frames=420):
    t.check("%s: CRC and size match" % what, tr.get("crc_ok") and tr.get("size_ok"), strip(tr))
    t.check("%s: about 30 s of video (>= %d frames, no gaps, valid JPEG markers)" % (what, min_frames),
            tr.get("frames", 0) >= min_frames and tr.get("seq_gaps", 1) == 0 and tr.get("bad_frames", 1) == 0,
            "frames=%s gaps=%s bad=%s" % (tr.get("frames"), tr.get("seq_gaps"), tr.get("bad_frames")))
    t.check("%s: 30 s of stereo audio" % what, abs(tr.get("audio_s", 0) - 30) < 0.1, tr.get("audio_s"))


# ============================================================ tests
def t_boot(ph, t):
    _, m = ph.wait_line(r"^BOOT (.*)", 5)
    b = dict(kv.split("=") for kv in m.group(1).split())
    t.metrics["boot"] = b
    t.check("two CPU cores", b["cores"] == "2", b["cores"])
    t.check("8 MB flash", int(b["flash"]) == 8 * 1024 * 1024, b["flash"])
    t.check("8 MB PSRAM detected (octal)", int(b["psram_total"]) >= 8 * 1024 * 1024 - 64 * 1024, b["psram_total"])
    t.check("starts in Sleep", ph.find_lines(r"^STATE sleep"))
    t.check("phone connects over BLE", wait(ph, r"ble_connected", 15))
    time.sleep(3)
    t.check("HELLO sent to phone", any(n == "HELLO" for _, n, _ in ph.msgs))
    t.check("camera and Wi-Fi stay off in Sleep", not ph.find_lines(r"EV fps=[1-9]|WIFI on"))
    t.check("no audio streamed in Sleep", ph.audio["pkts"] == 0, ph.audio["pkts"])


def t_listen_stream(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    t.check("voice line 'listening'", wait(ph, r"VOICE \d+ listening", 5))
    t.check("camera on at 15 fps", wait(ph, r"EV fps=15", 5))
    time.sleep(3)
    p0, t0 = ph.audio["pkts"], time.time()
    s0 = fresh_stats(ph)
    time.sleep(20)
    s1 = fresh_stats(ph)
    dt = (s1["t_ms"] - s0["t_ms"]) / 1000
    rate = (ph.audio["pkts"] - p0) / (time.time() - t0)
    kBps = rate * 408 / 1000
    fps = (s1["frames_written"] - s0["frames_written"]) / dt
    t.metrics.update(stream_kBps=round(kBps, 2), fps=round(fps, 2))
    t.check("compressed audio stream about 8 KB/s (ADPCM, 50 ms packets)", 7.0 < kBps < 9.5, "%.2f KB/s" % kBps)
    t.check("no gaps in the audio stream", ph.audio["gaps"] == 0, ph.audio["gaps"])
    r = sim.goertzel_ratio(ph.audio["samples"][-8000:], 440)
    t.check("phone decodes the 440 Hz test voice from ADPCM", r > 0.8, "%.3f of power at 440 Hz" % r)
    t.check("video written at 15 fps", 14.0 < fps < 16.0, "%.2f fps" % fps)
    t.check("no dropped frames", s1["drop_wbuf"] == 0 and s1["drop_cam"] == 0, (s1["drop_wbuf"], s1["drop_cam"]))


def t_rolling(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(75)
    s = fresh_stats(ph)
    t.metrics.update(sd_written=s["sd_written"], sd_used=s["sd_used"], chunks=s["chunks"])
    t.check("about 70 MB written to the card", s["sd_written"] > 60e6, s["sd_written"])
    t.check("rolling buffer stays at 15 chunks + the open one", s["chunks"] <= 16, s["chunks"])
    t.check("card space used stays near 30 MB (old chunks deleted)", s["sd_used"] < 40e6, s["sd_used"])
    t.check("no dropped frames", s["drop_wbuf"] == 0, s["drop_wbuf"])


def t_button_save(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(35)
    t.check("Wi-Fi off before any clip is saved", not ph.find_lines(r"WIFI on"))
    m = ph.mark()
    ph.tap("SB")
    t.check("short press in Listen saves a clip", wait(ph, r"clip_saved id=1 trigger=button", 20, m))
    t.check("voice line 'clip saved'", wait(ph, r"VOICE \d+ clip_saved", 10, m))
    i_on, _ = ph.wait_line(r"WIFI on", 20, m)
    t.check("Wi-Fi switched on for the transfer", i_on is not None)
    t.check("clip confirmed by phone", wait(ph, r"xfer_done id=1 result=confirmed", 150, m))
    t.check("clip deleted from card only after confirmation", wait(ph, r"clip_deleted id=1", 10, m))
    i_off, _ = ph.wait_line(r"WIFI off", 10, m)
    t.check("Wi-Fi switched off after the transfer", i_off is not None)
    tr = [x for x in ph.transfers if x.get("result") == "ok"]
    if t.check("phone received the clip", tr):
        clip_ok(t, tr[0], "button clip")
        t.metrics["transfer_s_while_recording"] = tr[0]["seconds"]
        t.metrics["clip_bytes"] = tr[0]["bytes"]
    t.check("recording kept running during the save and transfer", stats(ph).get("drop_wbuf", 1) == 0)


def t_phone_save(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(33)
    m = ph.mark()
    ph.send_cmd(cmd="save", phrase="due friday")
    t.check("phone key-phrase command saves a clip", wait(ph, r"clip_saved id=1 trigger=phone", 20, m))
    t.check("clip confirmed and deleted", wait(ph, r"clip_deleted id=1", 150, m))
    tr = [x for x in ph.transfers if x.get("result") == "ok"]
    if t.check("phone received the clip", tr):
        clip_ok(t, tr[0], "phone clip")
        t.check("clip metadata records the phrase", tr[0]["meta"].get("phrase") == "due friday", tr[0]["meta"])
    m = ph.mark()
    ph.send_cmd(cmd="stop")
    t.check("phone 'stop' command ends Listen", wait(ph, r"STATE sleep", 30, m))
    m = ph.mark()
    ph.send_cmd(cmd="save", phrase="exam")
    t.check("save command ignored in Sleep", wait(ph, r"save_ignored reason=not_listening", 10, m))
    m = ph.mark()
    ph.send_cmd(cmd="listen")
    t.check("phone 'listen' command starts Listen", wait(ph, r"STATE listen", 10, m))


def t_confirm_before_delete(ph, t):
    wait(ph, r"ble_connected", 15)
    ph.wifi_plan = ["nack", "noack"]
    start_listen(ph, t)
    time.sleep(33)
    m = ph.mark()
    ph.tap("SB")
    i1, _ = ph.wait_line(r"xfer_fail reason=nack id=1", 150, m)
    t.check("phone reports a bad copy (NACK): transfer marked failed", i1 is not None)
    t.check("clip NOT deleted after NACK", not ph.find_lines(r"clip_deleted", m))
    i2, _ = ph.wait_line(r"xfer_fail reason=link id=1", 200, i1 or m)
    t.check("no confirmation (ACK timeout): transfer marked failed", i2 is not None)
    t.check("clip still NOT deleted without confirmation", not ph.find_lines(r"clip_deleted", m))
    t.check("third attempt confirmed, then deleted", wait(ph, r"clip_deleted id=1", 200, i2 or m))
    oks = [x for x in ph.transfers if x.get("result") == "ok"]
    if t.check("good copy received on the retry", oks):
        clip_ok(t, oks[-1], "retried clip")


def t_transfer_failed(ph, t):
    wait(ph, r"ble_connected", 15)
    ph.wifi_plan = ["refuse", "drop_mid"]
    start_listen(ph, t)
    time.sleep(33)
    m = ph.mark()
    ph.tap("SB")
    i1, _ = ph.wait_line(r"xfer_fail reason=(wifi_connect|link)", 60, m)
    t.check("phone refuses the Wi-Fi connection: transfer failed", i1 is not None)
    t.check("connection dropped mid-transfer: transfer failed", wait(ph, r"xfer_fail reason=link id=1", 200, (i1 or m) + 1))
    t.check("clip retried and confirmed", wait(ph, r"clip_deleted id=1", 200, m))
    fw = [l[1] for _, l in ph.find_lines(r"WIFI on", m)]
    gaps = [(b - a) / 1000 for a, b in zip(fw, fw[1:])]
    t.metrics["retry_gaps_s"] = gaps
    t.check("Wi-Fi switched off after every attempt", len(ph.find_lines(r"WIFI off", m)) >= len(fw) - 1 >= 2,
            (len(fw), len(ph.find_lines(r"WIFI off", m))))
    t.check("retry waits at least 5 s after a failure", gaps and gaps[0] >= 5.0, gaps)
    oks = [x for x in ph.transfers if x.get("result") == "ok"]
    if t.check("good copy received", oks):
        clip_ok(t, oks[-1], "clip after failures")


def t_phone_lost_listen(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(32)
    m = ph.mark()
    ph.go_away()
    t.check("earpiece notices the phone is gone", wait(ph, r"phone_disconnected state=listen", 15, m))
    t.check("voice line 'phone disconnected'", wait(ph, r"VOICE \d+ phone_disconnected", 5, m))
    s0 = fresh_stats(ph)
    ph.tap("SB")
    t.check("button save still works offline (clip 1)", wait(ph, r"clip_saved id=1", 20, m))
    time.sleep(6)
    m2 = ph.mark()
    ph.tap("SB")
    t.check("second offline save (clip 2)", wait(ph, r"clip_saved id=2", 20, m2))
    t.check("offline queue waits for the phone", wait(ph, r"xfer_wait reason=phone_not_connected pending=2", 15, m2))
    time.sleep(10)
    s1 = fresh_stats(ph)
    t.check("still recording while offline", s1["frames_written"] > s0["frames_written"] + 200,
            (s0["frames_written"], s1["frames_written"]))
    tries = [l[1] for _, l in ph.find_lines(r"ble_retry", m)]
    gaps = [(b - a) / 1000 for a, b in zip(tries, tries[1:])]
    t.metrics["ble_retry_gaps_s"] = gaps
    t.check("reconnect tried every 5 s", gaps and all(4.5 <= g <= 6.5 for g in gaps), gaps)
    m3 = ph.mark()
    ph.come_back()
    t.check("reconnects when the phone returns", wait(ph, r"ble_connected", 10, m3))
    t.check("voice line 'phone connected'", wait(ph, r"VOICE \d+ phone_connected", 5, m3))
    t.check("both queued clips sent and deleted", wait(ph, r"clip_deleted id=1", 200, m3) and wait(ph, r"clip_deleted id=2", 200, m3))
    oks = [x for x in ph.transfers if x.get("result") == "ok"]
    t.check("phone has both clips", sorted(x["id"] for x in oks) == [1, 2], [x["id"] for x in oks])
    if oks:
        clip_ok(t, oks[0], "offline clip 1")
        t.check("offline clip 2 valid (shorter: clip 1 took the older chunks)",
                oks[-1]["crc_ok"] and oks[-1]["seq_gaps"] == 0 and oks[-1]["frames"] > 60, strip(oks[-1]))
    t.check("no dropped frames during the dropout", stats(ph)["drop_wbuf"] == 0)


def t_long_press_stop(ph, t):
    wait(ph, r"ble_connected", 15)
    ph.wifi_plan = ["refuse"]
    start_listen(ph, t)
    time.sleep(33)
    m = ph.mark()
    ph.tap("SB")
    wait(ph, r"xfer_fail reason=wifi_connect", 60, m)
    m = ph.mark()
    ph.hold("SB", 1500)
    t.check("long press stops Listen", wait(ph, r"button sb=long state=listen", 10, m))
    t.check("voice line 'stopped listening'", wait(ph, r"VOICE \d+ stopped_listening", 5, m))
    t.check("camera off (mic + camera off)", wait(ph, r"EV fps=0", 5, m))
    t.check("waits for queued clips before Sleep", wait(ph, r"waiting_for_queue pending=1", 5, m))
    t.check("queued clip sent during the wait", wait(ph, r"clip_deleted id=1", 120, m))
    t.check("then goes to Sleep", wait(ph, r"stop_done pending=0", 10, m) and wait(ph, r"STATE sleep", 5, m))
    p = ph.audio["pkts"]
    time.sleep(5)
    t.check("audio stream stopped", ph.audio["pkts"] == p, (p, ph.audio["pkts"]))
    t.check("rolling buffer deleted on stop", wait(ph, r"storage_stopped", 5, m))


def t_prompt_listen(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(8)
    s0 = fresh_stats(ph)
    m = ph.mark()
    ph.hold("PR", 3000)
    t.check("Prompt button enters Prompt state", wait(ph, r"STATE prompt", 5, m))
    sent = wait(ph, r"prompt_sent id=1 samples=(\d+) adpcm=(\d+) frame=(\d+) ok=1", 15, m)
    if t.check("voice + latest frame sent to phone", sent):
        t.check("about 3 s of prompt audio", 40000 < int(sent.group(1)) < 56000, sent.group(1))
        t.check("frame is a ~60 KB JPEG", 45000 < int(sent.group(3)) < 90000, sent.group(3))
    t.check("phone receives the prompt", wait(ph, r"SPK_PCM", 15, m))
    if ph.prompts:
        p = ph.prompts[-1]
        t.check("phone gets valid JPEG and the voice", p.get("frame_ok") and p.get("audio_440", 0) > 0.5,
                {k: v for k, v in p.items() if k != "begin"})
    t.check("answer played, back to Listen with recording still on", wait(ph, r"prompt_end id=1 why=answered back_to=listen", 15, m))
    s1 = fresh_stats(ph)
    t.check("recording continued during the prompt (no dropped frames)",
            s1["drop_wbuf"] == 0 and s1["frames_written"] - s0["frames_written"] > 15 * 5, (s0["frames_written"], s1["frames_written"]))
    p = ph.audio["pkts"]
    time.sleep(3)
    t.check("live audio stream resumes after the prompt", ph.audio["pkts"] > p + 40)


def t_prompt_sleep(ph, t):
    wait(ph, r"ble_connected", 15)
    m = ph.mark()
    ph.hold("PR", 2000)
    t.check("Prompt from Sleep", wait(ph, r"STATE prompt", 5, m))
    sent = wait(ph, r"prompt_sent id=1 samples=(\d+) adpcm=(\d+) frame=(\d+) ok=1", 15, m)
    t.check("frame captured from Sleep (camera on briefly)", sent and int(sent.group(3)) > 40000)
    t.check("back to Sleep after the answer", wait(ph, r"prompt_end id=1 why=answered back_to=sleep", 15, m))
    time.sleep(2)
    t.check("nothing recorded and no stream from Sleep", stats(ph).get("frames_written", 0) == 0 and ph.audio["pkts"] == 0)


def t_prompt_errors(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    ph.reply_mode = "fail"
    m = ph.mark()
    ph.hold("PR", 1500)
    t.check("LLM failure: error voice line", wait(ph, r"VOICE \d+ sorry_couldnt_answer", 20, m))
    t.check("LLM failure: back to Listen", wait(ph, r"prompt_end id=1 why=llm_failed back_to=listen", 10, m))
    ph.reply_mode = "none"
    m = ph.mark()
    ph.hold("PR", 1500)
    t.check("no answer: times out after 15 s", wait(ph, r"prompt_timeout id=2", 30, m))
    t.check("timeout: error voice line", wait(ph, r"VOICE \d+ sorry_couldnt_answer", 5, m))
    t.check("timeout: back to Listen", wait(ph, r"prompt_end id=2 why=timeout back_to=listen", 10, m))
    ph.reply_mode = "none"
    m = ph.mark()
    ph.hold("PR", 1500)
    wait(ph, r"prompt_sent id=3", 15, m)
    ph.go_away()
    t.check("phone lost during prompt: offline voice line", wait(ph, r"VOICE \d+ phone_disconnected", 15, m))
    t.check("phone lost during prompt: back to previous state (Listen)", wait(ph, r"prompt_end id=3 why=phone_lost back_to=listen", 10, m))
    m = ph.mark()
    ph.hold("PR", 1000)
    t.check("prompt while phone is away: offline voice line, stays in Listen",
            wait(ph, r"prompt_offline state=listen", 10, m) and not ph.find_lines(r"STATE prompt", m))
    ph.come_back()
    t.check("reconnects", wait(ph, r"ble_connected", 15, m))


def t_prompt_approval(ph, t):
    wait(ph, r"ble_connected", 15)
    ph.reply_mode = "approval"
    m = ph.mark()
    ph.hold("PR", 1500)
    t.check("database edit: approval voice line", wait(ph, r"VOICE \d+ approve_change", 20, m))
    ph.tap("PR")
    t.check("short Prompt press = approve", wait(ph, r"approval id=1 approved=1 how=short", 10, m))
    m = ph.mark()
    ph.hold("PR", 1500)
    wait(ph, r"VOICE \d+ approve_change", 20, m)
    ph.hold("PR", 1500)
    t.check("long Prompt press = refuse", wait(ph, r"approval id=2 approved=0 how=long", 10, m))
    m = ph.mark()
    ph.hold("PR", 1500)
    wait(ph, r"VOICE \d+ approve_change", 20, m)
    t.check("no press in 10 s = refuse", wait(ph, r"approval id=3 approved=0 how=timeout", 20, m))
    time.sleep(1.5)
    t.check("phone received all three answers", [a["approved"] for a in ph.approvals] == [True, False, False], ph.approvals)


def t_thermal(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(4)
    m = ph.mark()
    ph.bench("TEMP 68")
    t.check("65 C: frame rate lowered to 10 fps", wait(ph, r"thermal level=1 .* fps_cap=10", 5, m) and wait(ph, r"EV fps=10", 5, m))
    ph.bench("TEMP 78")
    t.check("75 C: 5 fps and 'too hot' voice line", wait(ph, r"EV fps=5", 5, m) and wait(ph, r"VOICE \d+ too_hot", 5, m))
    time.sleep(31)
    m2 = ph.mark()
    ph.tap("SB")
    wait(ph, r"clip_saved id=1", 20, m2)
    time.sleep(8)
    t.check("75 C: clip kept, Wi-Fi transfers held back", not ph.find_lines(r"WIFI on", m2))
    ph.bench("TEMP 88")
    p = ph.audio["pkts"]
    t.check("85 C: camera off", wait(ph, r"EV fps=0", 5, m2))
    time.sleep(4)
    t.check("85 C: audio keeps recording and streaming", ph.audio["pkts"] > p + 40, ph.audio["pkts"] - p)
    m3 = ph.mark()
    ph.bench("TEMP 50")
    t.check("cooled: back to 15 fps, 'cooled down' voice line", wait(ph, r"EV fps=15", 5, m3) and wait(ph, r"VOICE \d+ cooled_down", 5, m3))
    t.check("cooled: held clip now sent", wait(ph, r"clip_deleted id=1", 150, m3))


def t_battery(ph, t):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(3)
    m = ph.mark()
    ph.bench("BATT 14")
    t.check("15%: 'low battery' voice line", wait(ph, r"VOICE \d+ low_battery", 5, m))
    t.check("15%: power saving, 10 fps", wait(ph, r"EV fps=10", 5, m))
    ph.bench("BATT 4")
    t.check("5%: 'battery critical' voice line", wait(ph, r"VOICE \d+ battery_critical", 5, m))
    t.check("5%: recording stopped cleanly and Sleep", wait(ph, r"storage_stopped", 10, m) and wait(ph, r"STATE sleep", 5, m))
    m2 = ph.mark()
    ph.tap("SB")
    time.sleep(2)
    t.check("5%: Listen refused", not ph.find_lines(r"STATE listen", m2) and wait(ph, r"VOICE \d+ battery_critical", 3, m2))
    ph.bench("BATT 60")
    time.sleep(2)
    m3 = ph.mark()
    ph.tap("SB")
    t.check("charged: Listen works again at 15 fps", wait(ph, r"STATE listen", 5, m3) and wait(ph, r"EV fps=15", 5, m3))


def t_storage_full(ph, t):
    wait(ph, r"ble_connected", 15)
    ph.go_away()
    start_listen(ph, t)
    time.sleep(32)
    ids = []
    for k in range(4):
        m = ph.mark()
        ph.tap("SB")
        r = wait(ph, r"clip_saved id=(\d+)|save_refused", 30, m)
        ids.append(r.group(0) if r else None)
        time.sleep(32)
    t.metrics["saves"] = ids
    t.check("saves refused when the card is nearly full", any(x and "refused" in x for x in ids), ids)
    t.check("'storage full' voice line", ph.find_lines(r"VOICE \d+ storage_full"))
    t.check("recording continues", stats(ph).get("drop_wbuf", 1) == 0 and stats(ph).get("state") == "listen")


def t_no_card(ph, t):
    t.check("boot reports the missing card", ph.find_lines(r"storage_failed"))
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    t.check("voice line 'memory card problem'", wait(ph, r"VOICE \d+ memory_card_problem", 5))
    time.sleep(8)
    t.check("live audio stream still works", ph.audio["pkts"] > 100, ph.audio["pkts"])
    m = ph.mark()
    ph.tap("SB")
    t.check("clip save refused, not a crash", wait(ph, r"save_refused reason=no_card", 10, m))
    ph.hold("PR", 1500)
    t.check("prompts still work", wait(ph, r"prompt_end id=1 why=answered back_to=listen", 20, m))


def speed_case(ph, t, label):
    wait(ph, r"ble_connected", 15)
    start_listen(ph, t)
    time.sleep(33)
    m = ph.mark()
    ph.tap("SB")
    wait(ph, r"clip_saved id=1", 30, m)
    time.sleep(20)
    ph.bench("SD_STALL 1500")      # a long card pause in the middle of a transfer
    time.sleep(20)
    ph.send_cmd(cmd="save", phrase="on the exam")
    wait(ph, r"clip_saved id=2", 30, m)
    ok = wait(ph, r"clip_deleted id=2", 400, m)
    time.sleep(4)
    s = fresh_stats(ph)
    times = ph.audio["times"]
    gaps = [b - a for a, b in zip(times, times[1:])]
    tr = [x for x in ph.transfers if x.get("result") == "ok"]
    fps_changes = [l[2] for _, l in ph.find_lines(r"EV (fps=|backpressure)")]
    t.metrics.update(label=label, wbuf_hwm=s["wbuf_hwm"], wbuf_hwm_pct=round(100 * s["wbuf_hwm"] / s["wbuf_size"], 1),
                     drop_wbuf=s["drop_wbuf"], drop_cam=s["drop_cam"], frames_written=s["frames_written"],
                     max_write_ms=s["max_write_ms"], sd_pauses=s["sd_pauses"], sd_pause_ms=s["sd_pause_ms"],
                     transfer_s=[x["seconds"] for x in tr], transfer_MB=[round(x["bytes"] / 1e6, 1) for x in tr],
                     clip_frames=[x["frames"] for x in tr], clip_gaps=[x["seq_gaps"] for x in tr],
                     audio_stream_max_gap_s=round(max(gaps), 2) if gaps else None, stream_gaps=ph.audio["gaps"],
                     stream_drops=s["stream_drops"], fps_events=fps_changes, int_min=s["int_min"], ps_min=s["ps_min"],
                     audio_overwritten=s["audio_overwritten"])
    t.check("both clips transferred while recording", ok and len(tr) == 2, len(tr))
    return s, gaps, tr


def t_speed_good_ble50(ph, t):
    s, gaps, tr = speed_case(ph, t, "good card, BLE 50 KB/s")
    t.check("no frames dropped (write buffer never overflowed)", s["drop_wbuf"] == 0 and s["drop_cam"] == 0, (s["drop_wbuf"], s["drop_cam"]))
    t.check("audio stream continuous while Wi-Fi shares the radio (no gap > 0.5 s)", gaps and max(gaps) < 0.5, max(gaps) if gaps else None)
    t.check("clips complete", all(x["seq_gaps"] == 0 for x in tr))


def t_speed_good_ble100(ph, t):
    s, gaps, tr = speed_case(ph, t, "good card, BLE 100 KB/s")
    t.check("no frames dropped", s["drop_wbuf"] == 0 and s["drop_cam"] == 0, (s["drop_wbuf"], s["drop_cam"]))
    t.check("audio stream continuous (no gap > 0.5 s)", gaps and max(gaps) < 0.5, max(gaps) if gaps else None)


def t_speed_cheap(ph, t):
    s, gaps, tr = speed_case(ph, t, "cheap card (3x slower), BLE 50 KB/s")
    t.metrics["note"] = "pass = firmware degrades gracefully (lower fps, valid clips), not zero drops"
    t.check("firmware lowers the frame rate when the card falls behind", ph.find_lines(r"backpressure fps_cap=(10|5)"))
    t.check("clips still valid", tr and all(x["crc_ok"] for x in tr))
    t.check("audio stream continuous (no gap > 0.5 s)", gaps and max(gaps) < 0.5, max(gaps) if gaps else None)


TESTS = [
    ("boot", "Boot on XIAO-spec emulator, Sleep state", t_boot, {}, {}),
    ("listen_stream", "Listen state + compressed audio stream", t_listen_stream, {}, {}),
    ("rolling_buffer", "30 s rolling buffer on the card", t_rolling, {}, {}),
    ("button_save", "Second Brain short press saves a clip; Wi-Fi only during transfer", t_button_save, {}, {}),
    ("phone_save", "Phone key-phrase save command; phone listen/stop commands", t_phone_save, {}, {}),
    ("confirm_before_delete", "Clip deleted only after phone confirms", t_confirm_before_delete, {}, {}),
    ("transfer_failed", "Transfer-failed path: retry every 5 s", t_transfer_failed, {}, {}),
    ("phone_lost_listen", "Phone-lost path in Listen + offline queue", t_phone_lost_listen, {}, {}),
    ("long_press_stop", "Long press stops Listen, waits for queue, Sleep", t_long_press_stop, {}, {}),
    ("prompt_listen", "Prompt from Listen (voice + frame, answer, back to Listen)", t_prompt_listen, {}, {}),
    ("prompt_sleep", "Prompt from Sleep", t_prompt_sleep, {}, {}),
    ("prompt_errors", "Prompt error paths: LLM fail, timeout, phone lost", t_prompt_errors, {}, {}),
    ("prompt_approval", "Database-edit approval with the Prompt button", t_prompt_approval, {}, {}),
    ("thermal", "Temperature throttling", t_thermal, dict(temp_model=0), {}),
    ("battery", "Low and critical battery", t_battery, {}, {}),
    ("storage_full", "Card nearly full: saves refused", t_storage_full, {}, dict(sd_mb=128)),
    ("no_card", "No or broken microSD card", t_no_card, {}, dict(sd_mb=0)),
    ("speed_good_ble50", "Speed model: good card, BLE 50 KB/s", t_speed_good_ble50, dict(sim.GOOD_CARD, temp_model=0, **sim.BLE_SLOW), {}),
    ("speed_good_ble100", "Speed model: good card, BLE 100 KB/s", t_speed_good_ble100, dict(sim.GOOD_CARD, temp_model=0, **sim.BLE_FAST), {}),
    ("speed_cheap_card", "Speed model: cheap card 3x slower", t_speed_cheap, dict(sim.CHEAP_CARD, temp_model=0, **sim.BLE_SLOW), {}),
]


def run_one(build, outdir, spec, seed):
    name, title, fn, cfg, boot_kw = spec
    t = T(name)
    t0 = time.time()
    work = os.path.join(outdir, name)
    ph = emu = None
    try:
        ph, emu = sim.boot(build, work, extra_cfg=cfg, seed=seed, **boot_kw)
        wait(ph, r"ble_connected", 20)
        ph.send_cmd(cmd="stats", period=2)
        fn(ph, t)
        ph.send_cmd(cmd="tasks")
        _, m = ph.wait_line(r"^TASKS (.*)", 5)
        if m:
            t.metrics["stack_free_words"] = json.loads(m.group(1))
        s = fresh_stats(ph)
        t.metrics.update(final_int_min=s.get("int_min"), final_ps_min=s.get("ps_min"), final_wbuf_hwm=s.get("wbuf_hwm"))
        t.series = ph.stats
    except Exception as e:  # noqa: BLE001
        t.check("test ran without harness error", False, "%s\n%s" % (e, traceback.format_exc()))
    finally:
        if emu:
            emu.stop()
        if ph:
            ph.close()
    crashed = False
    try:
        crashed = any(k in open(os.path.join(work, "serial.log"), errors="replace").read()
                      for k in ("Guru Meditation", "abort()", "panic", "stack overflow"))
    except OSError:
        pass
    t.check("firmware did not crash", not crashed)
    return dict(name=name, title=title, passed=t.passed, seconds=round(time.time() - t0), checks=t.checks,
                metrics=t.metrics, series=getattr(t, "series", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="/tmp/te-sim")
    ap.add_argument("--out", default="/tmp/te-tests")
    ap.add_argument("--only", default="")
    ap.add_argument("-j", type=int, default=2)
    ap.add_argument("--results", default=os.path.join(sim.PROJECT, "results", "test-results.json"))
    a = ap.parse_args()
    specs = [s for s in TESTS if not a.only or s[0] in a.only.split(",")]
    with ThreadPoolExecutor(a.j) as ex:
        res = list(ex.map(lambda sp: run_one(a.build, a.out, sp, seed=1 + TESTS.index(sp)), specs))
    for r in res:
        print("%-22s %s  (%ds)" % (r["name"], "PASS" if r["passed"] else "FAIL", r["seconds"]))
        for c in r["checks"]:
            if not c["ok"]:
                print("    FAILED: %s -- %s" % (c["check"], c["detail"][:300]))
    os.makedirs(os.path.dirname(a.results), exist_ok=True)
    old = {}
    if os.path.exists(a.results) and a.only:
        old = {r["name"]: r for r in json.load(open(a.results))}
    for r in res:
        old[r["name"]] = r
    order = [s[0] for s in TESTS]
    json.dump(sorted(old.values(), key=lambda r: order.index(r["name"])), open(a.results, "w"), indent=1)
    print("%d/%d passed" % (sum(r["passed"] for r in res), len(res)))


if __name__ == "__main__":
    main()
