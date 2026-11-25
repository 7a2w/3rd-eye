#!/usr/bin/env python3
"""One-hour lecture recording in the emulator, with the speed model on
("Test first" in docs/software-design.md section 4).

Runs in real time (QEMU's clock follows the host clock). Timeline:
  0:00 Listen on (button)          26:00 button save while the phone is away
  5:00 button save                 28:00 phone back, offline clip sent
 12:00 phone key-phrase save       35:00 phone key-phrase save
 20:00 prompt (3 s question)       45:00 button save
 25:00 phone dropout (3 min)       52:00 phone key-phrase save
                                   60:00 long press: stop, wait for queue, Sleep

  python tools/run_lecture.py --build /tmp/te-sim [--minutes 60] [--card good|cheap]
"""
import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="/tmp/te-sim")
    ap.add_argument("--work", default="/tmp/te-lecture")
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--card", default="good")
    ap.add_argument("--stats-period", type=int, default=15)
    ap.add_argument("--out", default=os.path.join(sim.PROJECT, "results"))
    a = ap.parse_args()
    scale = a.minutes / 60.0
    card = sim.GOOD_CARD if a.card == "good" else sim.CHEAP_CARD
    cfg = dict(card, ble_Bps=60000, temp_model=1, batt_mah=1200, batt_start_pct=100)
    ph, emu = sim.boot(a.build, a.work, extra_cfg=cfg, seed=2026, sd_mb=1024)
    log = []

    def ev(what):
        log.append(dict(t_min=round((time.time() - t0) / 60, 2), fw_ms=ph.fw_ms(), what=what))
        print("%6.2f min  %s" % ((time.time() - t0) / 60, what), flush=True)

    ph.wait_line(r"ble_connected", 30)
    ph.send_cmd(cmd="stats", period=a.stats_period)
    t0 = time.time()
    plan = [
        (0.0, "listen", lambda: ph.tap("SB")),
        (5.0, "button save", lambda: ph.tap("SB")),
        (12.0, "phone save 'due friday'", lambda: ph.send_cmd(cmd="save", phrase="due friday")),
        (20.0, "prompt (3 s question)", lambda: ph.hold("PR", 3000)),
        (25.0, "phone dropout starts", ph.go_away),
        (26.0, "button save while phone away", lambda: ph.tap("SB")),
        (28.0, "phone back", ph.come_back),
        (35.0, "phone save 'on the exam'", lambda: ph.send_cmd(cmd="save", phrase="on the exam")),
        (45.0, "button save", lambda: ph.tap("SB")),
        (52.0, "phone save 'assignment'", lambda: ph.send_cmd(cmd="save", phrase="assignment")),
        (59.5, "task stack report", lambda: ph.send_cmd(cmd="tasks")),
        (60.0, "long press: stop Listen", lambda: ph.hold("SB", 1500)),
    ]
    for at, what, fn in plan:
        at *= scale
        while time.time() - t0 < at * 60:
            time.sleep(1)
        fn()
        ev(what)
    ph.wait_line(r"stop_done", 300)
    ph.wait_line(r"STATE sleep", 30)
    time.sleep(a.stats_period + 5)
    ev("end")
    emu.stop()
    ph.close()

    st = ph.stats
    os.makedirs(a.out, exist_ok=True)
    name = "lecture-%dmin-%s" % (round(a.minutes), a.card)
    keys = ["t_ms", "state", "fps", "int_free", "int_min", "int_largest", "ps_free", "ps_min", "ps_largest",
            "wbuf_used", "wbuf_hwm", "frames_in", "frames_written", "drop_wbuf", "drop_cam", "stream_pkts",
            "stream_drops", "sd_written", "sd_read", "sd_used", "sd_pauses", "sd_pause_ms", "max_write_ms",
            "clips_saved", "clips_sent", "pending", "xfer_fail", "ble", "wifi", "batt_pct", "mah_used",
            "current_ma", "temp", "cpu0", "cpu1"]
    with open(os.path.join(a.out, name + ".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, keys, extrasaction="ignore")
        w.writeheader()
        for s in st:
            w.writerow(s)
    lis = [s for s in st if s["state"] == "listen" and not s["wifi"]]
    tasks = [l[2] for _, l in ph.find_lines(r"^TASKS ")]
    summary = dict(
        minutes=a.minutes, card=a.card, timeline=log,
        recorded_s=round((lis[-1]["t_ms"] - lis[0]["t_ms"]) / 1000) if lis else 0,
        frames_in=st[-1]["frames_in"], frames_written=st[-1]["frames_written"],
        dropped_write_buffer=st[-1]["drop_wbuf"], dropped_camera_driver=st[-1]["drop_cam"],
        wbuf_hwm=st[-1]["wbuf_hwm"], wbuf_size=st[-1]["wbuf_size"],
        stream_pkts=st[-1]["stream_pkts"], stream_drops=st[-1]["stream_drops"],
        sd_written=st[-1]["sd_written"], sd_read=st[-1]["sd_read"], sd_used_max=max(s["sd_used"] for s in st),
        sd_used_end=st[-1]["sd_used"], sd_pauses=st[-1]["sd_pauses"], sd_pause_ms=st[-1]["sd_pause_ms"],
        max_write_ms=st[-1]["max_write_ms"],
        clips_saved=st[-1]["clips_saved"], clips_sent=st[-1]["clips_sent"], xfer_fail=st[-1]["xfer_fail"],
        clips_received=sorted(ph.clips), clip_checks={k: {x: v[x] for x in ("frames", "seq_gaps", "audio_s", "crc_ok")}
                                                     for k, v in ph.clips.items()},
        transfers=[{k: v for k, v in t.items() if k != "meta"} for t in ph.transfers],
        int_free_listen_first=lis[0]["int_free"] if lis else None, int_free_listen_last=lis[-1]["int_free"] if lis else None,
        int_largest_listen_first=lis[0]["int_largest"] if lis else None, int_largest_listen_last=lis[-1]["int_largest"] if lis else None,
        ps_free_listen_first=lis[0]["ps_free"] if lis else None, ps_free_listen_last=lis[-1]["ps_free"] if lis else None,
        int_min=min(s["int_min"] for s in st), ps_min=min(s["ps_min"] for s in st),
        int_largest_min=min(s["int_largest"] for s in st), ps_largest_min=min(s["ps_largest"] for s in st),
        batt_pct_end=st[-1]["batt_pct"], mah_used=st[-1]["mah_used"],
        avg_current_ma=round(st[-1]["mah_used"] / ((st[-1]["t_ms"] - st[0]["t_ms"]) / 3.6e6), 1),
        temp_max=max(s["temp"] for s in st), audio_stream_gaps=ph.audio["gaps"],
        ble_connects=ph.ble_connects, voice_lines=[l[2] for _, l in ph.find_lines(r"^VOICE ")],
        backpressure=[l[2] for _, l in ph.find_lines(r"backpressure")], tasks=tasks,
        prompts=[{k: v for k, v in p.items() if k != "begin"} for p in ph.prompts],
    )
    json.dump(dict(summary=summary, series=st), open(os.path.join(a.out, name + ".json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("transfers", "timeline")}, indent=1))


if __name__ == "__main__":
    main()
