"""
Pre-drive smoke test for the model bake-off.

For each model named on the command line, runs a real logged camera frame
(with its real sensor readings) through the actual build_prompt -> model ->
parse_response pipeline the drive loop uses, and reports:

  - warm per-frame latency (model pre-warmed first; second call timed)
  - whether the model emitted a command our parser can read (go/no-go gate)
  - the model's observation / location / command / reasoning

Motors are NOT involved — this talks only to llama-swap. Purpose: don't spend
live drive time on a model that can't emit a valid command (lesson #801).

Usage:
  python -m scripts.model_smoketest gemma-4-26b-a4b cosmos-reason2-2b cosmos-reason2-8b
"""

import os
import sys
import time

from server.config import config, SEED_LOCATIONS
from server.vision_model import VisionModel
from server.command_generator import CommandGenerator
from shared.protocol import SensorData

FRAME = "training_data/sessions/20260526_114936_d0001d/frames/frame_000039.jpg"
# Real sensor readings logged alongside that frame, in mm (0 = dead/invalid;
# fc/rl/rr are dead hardware). Logs to cm: fl=49.5, fr=135.6, rest None.
SENSORS = SensorData(fc=0, fl=495, fr=1356, rl=0, rr=0)
GOAL = "Explore the environment and avoid obstacles"

# Tolerate cold model loads (gemma-4-26b-a4b is 22GB); the reported latency is
# taken from a warm call, so this only affects the load phase.
config.inference_timeout = 180.0

# Optional override to probe whether a "thinking" model just needs more room to
# reach the COMMAND: line (e.g. SMOKE_MAX_TOKENS=512).
config.max_new_tokens = int(os.environ.get("SMOKE_MAX_TOKENS", config.max_new_tokens))


def smoke(model: str, frame: bytes, prompt: str, cg: CommandGenerator) -> bool:
    print("=" * 64)
    print(f"MODEL: {model}")
    vm = VisionModel(model_name=model)
    try:
        vm.load()                      # triggers llama-swap load + warmup
        vm.process_frame(frame, prompt)  # warm the vision path (discard)
        t0 = time.time()
        resp = vm.process_frame(frame, prompt)
        latency_ms = int((time.time() - t0) * 1000)
    except Exception as e:
        print(f"  RESULT: FAIL (exception: {e})")
        return False
    finally:
        vm.unload()

    parsed = cg.parse_response(resp)
    ok = parsed.command is not None
    print(f"  warm latency : {latency_ms} ms")
    print(f"  PARSE        : {'OK' if ok else 'FAILED (no valid command)'}")
    print(f"  observation  : {(parsed.observation or '')[:140]}")
    print(f"  location     : {parsed.location}")
    print(f"  command      : {parsed.command}")
    print(f"  reasoning    : {(parsed.reasoning or '')[:120]}")
    print("  --- raw response (first 400 chars) ---")
    print("  " + resp[:400].replace("\n", "\n  "))
    print(f"  RESULT: {'PASS' if ok else 'NO-GO'}")
    return ok


def main():
    models = sys.argv[1:]
    if not models:
        print("usage: python -m scripts.model_smoketest <model> [<model> ...]")
        sys.exit(1)

    cg = CommandGenerator()
    prompt = cg.build_prompt(GOAL, sensor_data=SENSORS, known_locations=SEED_LOCATIONS)
    with open(FRAME, "rb") as f:
        frame = f.read()

    results = {m: smoke(m, frame, prompt, cg) for m in models}

    print("=" * 64)
    print("SUMMARY")
    for m, ok in results.items():
        print(f"  {'PASS ' if ok else 'NO-GO'}  {m}")


if __name__ == "__main__":
    main()
