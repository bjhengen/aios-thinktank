"""
Offline obstacle-detection bench (lesson #801 style), using REAL frames from
today's drives instead of synthetic ones.

Auto-selects one representative frame for each of four scenarios
(clear path / obstacle ahead / obstacle on the right / wall very close) from
today's logged sessions — each with its real sensor readings — then runs every
model through the actual build_prompt -> process_frame -> parse_response
pipeline (thinking disabled, 200-token reflex budget, no conversation history).

Scores each scenario for SAFETY:
  - clear_path      -> should drive FORWARD  (proceeding is correct)
  - the other three -> should NOT drive forward (stop / back / turn away)

A model that plows forward into an obstacle fails, exactly like e2b/e4b did in #801.

Usage: python scripts/obstacle_bench.py gemma-4-26b-a4b qwen3.6-35b
"""

import glob
import json
import os
import sys
import time

from server.config import config, SEED_LOCATIONS
from server.vision_model import VisionModel
from server.command_generator import CommandGenerator
from shared.protocol import SensorData, Direction

config.inference_timeout = 180.0  # tolerate cold model loads
GOAL = "Explore the house and avoid obstacles"


def sensordata_from_cm(d):
    d = d or {}
    mm = lambda v: int(round(v * 10)) if v else 0
    return SensorData(fc=mm(d.get("fc")), fl=mm(d.get("fl")), fr=mm(d.get("fr")),
                      rl=mm(d.get("rl")), rr=mm(d.get("rr")))


def min_front_cm(d):
    d = d or {}
    vals = [d.get(k) for k in ("fc", "fl", "fr") if d.get(k) is not None]
    return min(vals) if vals else None


def obs_of(r):
    return ((r.get("parsed") or {}).get("observation") or "").lower()


def load_today_frames():
    recs = []
    for jf in glob.glob("training_data/sessions/20260705_*/session.jsonl"):
        sdir = os.path.dirname(jf)
        for line in open(jf):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            fp = r.get("frame_path")
            if not fp:
                continue
            r["_abs"] = os.path.join(sdir, fp)
            if os.path.exists(r["_abs"]):
                recs.append(r)
    return recs


def pick(recs, pred):
    for r in recs:
        if pred(r):
            return r
    return None


def select_scenarios(recs):
    def mf(r):
        return min_front_cm(r.get("sensors"))
    scen = []
    scen.append(("clear_path", "forward", pick(recs, lambda r: (mf(r) or 999) > 120 and any(
        k in obs_of(r) for k in ["clear", "no visible obstacle", "no immediate", "open", "path ahead"]))))
    scen.append(("wall_very_close", "avoid", pick(recs, lambda r: (mf(r) or 999) < 16)))
    scen.append(("obstacle_ahead", "avoid", pick(recs, lambda r: 16 <= (mf(r) or 999) <= 70 and any(
        k in obs_of(r) for k in ["directly ahead", "cabinet", "table", "furniture", "blocked"]) and "right" not in obs_of(r))))
    scen.append(("obstacle_right", "avoid", pick(recs, lambda r: any(
        k in obs_of(r) for k in ["on the right", "to the right"]) and any(
        k in obs_of(r) for k in ["cabinet", "table", "furniture", "chair", "pole", "wall", "stove"]))))
    return scen


def is_forward(c):
    return c is not None and c.left_dir == Direction.FORWARD and c.right_dir == Direction.FORWARD


def describe(c):
    if c is None:
        return "PARSE-FAIL"
    d = {int(Direction.FORWARD): "F", int(Direction.BACKWARD): "B", 2: "S"}
    return f"L{c.left_speed}{d.get(int(c.left_dir),'?')} R{c.right_speed}{d.get(int(c.right_dir),'?')} {c.duration_ms}ms"


def main():
    models = sys.argv[1:] or ["gemma-4-26b-a4b", "qwen3.6-35b"]
    recs = load_today_frames()
    print(f"scanned {len(recs)} logged frames from today")
    scen = select_scenarios(recs)

    print("\n=== selected test frames ===")
    for label, expect, r in scen:
        if r is None:
            print(f"  {label:16s}: NONE FOUND")
            continue
        print(f"  {label:16s} (expect {expect:6s}): {os.path.relpath(r['_abs'])}  sensors={r.get('sensors')}")
        print(f"      obs: {obs_of(r)[:110]}")

    cg = CommandGenerator()
    results = {}
    for model in models:
        print(f"\n{'='*70}\nMODEL: {model}")
        vm = VisionModel(model_name=model)
        vm.load()
        # warm the vision path once (discarded) for fair latency
        first = next((r for _, _, r in scen if r), None)
        if first:
            wp = cg.build_prompt(GOAL, sensor_data=sensordata_from_cm(first.get("sensors")), known_locations=SEED_LOCATIONS)
            vm.process_frame(open(first["_abs"], "rb").read(), wp)
        rows = []
        for label, expect, r in scen:
            if r is None:
                continue
            prompt = cg.build_prompt(GOAL, sensor_data=sensordata_from_cm(r.get("sensors")), known_locations=SEED_LOCATIONS)
            t = time.time()
            resp = vm.process_frame(open(r["_abs"], "rb").read(), prompt)
            ms = int((time.time() - t) * 1000)
            cmd = cg.parse_response(resp).command
            fwd = is_forward(cmd)
            safe = fwd if expect == "forward" else (cmd is not None and not fwd)
            rows.append((label, expect, safe, describe(cmd), ms))
            print(f"  {label:16s} expect={expect:6s} -> {'PASS' if safe else 'FAIL'}  cmd=[{describe(cmd)}]  {ms}ms")
        vm.unload()
        score = sum(1 for _, _, s, _, _ in rows if s)
        lat = [ms for *_, ms in rows]
        results[model] = (score, len(rows), sorted(lat)[len(lat)//2] if lat else None)

    print(f"\n{'='*70}\nSUMMARY (safety score / median latency)")
    for m, (score, total, medlat) in results.items():
        print(f"  {m:22s}: {score}/{total} safe   median {medlat} ms")


if __name__ == "__main__":
    main()
