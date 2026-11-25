#!/usr/bin/env python3
"""CPU-load estimate using QEMU instruction counting (-icount shift=2).

With -icount, QEMU's clock advances 4 ns per guest instruction, so the
emulated CPU behaves like one that runs exactly 250 million instructions
per second. FreeRTOS run-time stats then show what share of that each core
is busy. This counts instructions only: it ignores cache misses, PSRAM wait
states and flash stalls, so the real load on the XIAO will be higher.

  python tools/cpu_estimate.py --build /tmp/te-sim
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402


def phase(ph, name, seconds, out):
    n = len(ph.stats)
    time.sleep(seconds)
    rows = [s for s in ph.stats[n + 1:]]   # skip the first sample: it spans the change
    if rows:
        out[name] = dict(samples=len(rows), cpu0=round(sum(r["cpu0"] for r in rows) / len(rows), 1),
                         cpu1=round(sum(r["cpu1"] for r in rows) / len(rows), 1),
                         cpu0_max=max(r["cpu0"] for r in rows), cpu1_max=max(r["cpu1"] for r in rows),
                         wifi=any(r["wifi"] for r in rows))
        print(name, out[name], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="/tmp/te-sim")
    ap.add_argument("--out", default=os.path.join(sim.PROJECT, "results", "cpu-estimate.json"))
    a = ap.parse_args()
    ph, emu = sim.boot(a.build, "/tmp/te-cpu", extra_cfg=dict(sim.GOOD_CARD), icount=2)
    ph.wait_line(r"ble_connected", 60)
    ph.send_cmd(cmd="stats", period=2)
    res = {}
    phase(ph, "sleep", 12, res)
    ph.tap("SB")
    ph.wait_line(r"STATE listen", 30)
    phase(ph, "listen", 40, res)
    m = ph.mark()
    ph.tap("SB")
    ph.wait_line(r"WIFI on", 60, m)
    phase(ph, "listen + clip transfer over Wi-Fi", 25, res)
    ph.wait_line(r"WIFI off", 300, m)
    emu.stop()
    ph.close()
    res["method"] = "QEMU -icount shift=2 (250 M instructions/s per core), FreeRTOS idle-task run time"
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
