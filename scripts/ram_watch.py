"""
Live ram/stall detector for a drive session.

Polls the newest training session's JSONL and raises ONE alert (then exits) when
the car looks stuck ramming: the last N commands are all pure-forward AND the
front sensors are pinned within a close band across those frames — the exact
signature of the dead-`fc` blind-spot bench incident (FL/FR read the side gaps
as "clear" so emergency-stop never fires, but nothing is actually moving).

In open space this stays quiet: with no obstacle, FL/FR read None, so `pinned`
is False and no alert fires.

Usage: python scripts/ram_watch.py [max_seconds] [n_forward] [close_cm]
Exits 0 on detection (prints the alert) or on timeout.
"""

import glob
import json
import os
import sys
import time

SESS_ROOT = "training_data/sessions"


def latest_session_jsonl():
    dirs = sorted(glob.glob(os.path.join(SESS_ROOT, "*")), key=os.path.getmtime)
    return os.path.join(dirs[-1], "session.jsonl") if dirs else None


def tail_records(path, k):
    try:
        with open(path) as f:
            lines = f.read().splitlines()[-k:]
        return [json.loads(l) for l in lines]
    except (OSError, ValueError):
        return []


def is_forward(rec):
    c = rec.get("command_final") or {}
    return c.get("left_dir") == 1 and c.get("right_dir") == 1


def front_min(rec):
    s = rec.get("sensors") or {}
    vals = [s.get(k) for k in ("fc", "fl", "fr") if s.get(k) is not None]
    return min(vals) if vals else None


def main():
    max_s = float(sys.argv[1]) if len(sys.argv) > 1 else 720.0
    n_fwd = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    close_cm = float(sys.argv[3]) if len(sys.argv) > 3 else 90.0

    start = time.time()
    alerted = None
    while time.time() - start < max_s:
        jsonl = latest_session_jsonl()
        recs = tail_records(jsonl, n_fwd) if jsonl else []
        if len(recs) >= n_fwd:
            window = recs[-n_fwd:]
            all_fwd = all(is_forward(r) for r in window)
            fmins = [front_min(r) for r in window]
            pinned = all(v is not None and v < close_cm for v in fmins)
            frame = window[-1].get("frame_num")
            if all_fwd and pinned and frame != alerted:
                obs = (window[-1].get("parsed") or {}).get("observation", "")[:130]
                print(f"POSSIBLE RAM/STALL @frame {frame}: {n_fwd} forward cmds, "
                      f"front pinned {fmins}cm. obs: {obs}")
                sys.exit(0)
        time.sleep(6)
    print("ram_watch: no ram detected before timeout")


if __name__ == "__main__":
    main()
