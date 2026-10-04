#!/usr/bin/env python3
"""Measure Linux process CPU, resident memory and virtual memory without a profiler."""

import argparse
import json
import os
import time
from pathlib import Path


def sample(pid):
    root = Path(f"/proc/{pid}")
    # comm is parenthesized and may contain spaces or closing parentheses.
    fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
    status = {}
    for line in (root / "status").read_text().splitlines():
        name, _, value = line.partition(":")
        if name in ("VmSize", "VmRSS", "VmHWM", "RssAnon", "Threads"):
            status[name] = int(value.split()[0])
    return {
        "at": time.monotonic(),
        "started": int(fields[19]),
        "ticks": int(fields[11]) + int(fields[12]),
        "vsz_kib": status["VmSize"],
        "rss_kib": status["VmRSS"],
        "peak_rss_kib": status["VmHWM"],
        "anonymous_kib": status.get("RssAnon"),
        "threads": status["Threads"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--samples", type=int, default=6)
    args = parser.parse_args()
    if args.pid <= 0 or not 0 < args.interval <= 3600 or args.samples <= 0:
        parser.error("positive PID/samples and interval in (0, 3600] required")
    hz = os.sysconf("SC_CLK_TCK")
    previous = sample(args.pid)
    print(json.dumps({"pid": args.pid, "initial": previous}), flush=True)
    for _ in range(args.samples):
        time.sleep(args.interval)
        current = sample(args.pid)
        if current["started"] != previous["started"]:
            raise SystemExit("Process restarted; start a new measurement")
        seconds = current["at"] - previous["at"]
        result = {
            key: value
            for key, value in current.items()
            if key not in ("ticks", "started")
        }
        result["seconds"] = round(seconds, 3)
        # 100% means one fully occupied core, independently of the core count.
        result["cpu_percent_one_core"] = round(
            100 * (current["ticks"] - previous["ticks"]) / hz / seconds, 3
        )
        print(json.dumps(result), flush=True)
        previous = current


if __name__ == "__main__":
    main()
