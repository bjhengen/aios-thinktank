# Robotcar Fine-Tune Runbook

**Status:** deferred — do this **after the chassis/camera rebuild** (the camera change shifts
the visual distribution, so a model trained on today's low-camera frames is throwaway).
**Goal:** distill the enforce-in-code corrections (`chosen` = code-corrected command,
`rejected` = raw AI command) into the driving model's weights — the AIOS thesis.
**Background:** claude-memory lessons **#1533** (reflex turn-direction fix) and **#1535** (POC findings).

---

## Assets already built (reuse — don't rebuild)

| Asset | Path | Notes |
|---|---|---|
| Dataset builder | `scripts/build_dpo_dataset.py` (committed) | → `training_data/dpo_pairs.jsonl`, **3,285 pairs**. `chosen` re-derived through the FIXED reflex chain so the old escape-direction bug isn't trained in. Re-run after new drives. |
| Train/test split | `training_data/dpo_{train,test}.jsonl` | Split by **whole session** (no frame leakage): 3,020 train / 265 test (137 reflex). |
| Eval harness | `scratchpad/eval_dpo.py` | base vs tuned on held-out frames. Metrics: chosen-action-match, prefers-correct-on-contested, unparsed rate. |
| TRL train attempt | `scratchpad/train_dpo.py` | Runs up to the model forward; **blocked** by TRL↔Qwen-VL (see gotchas). Kept for reference. |

**Baseline to beat** (base Qwen3-VL-8B, 160 held-out frames):
- chosen-action-match **20.6%** → want higher
- prefers-correct-on-contested **0%** (0/77) → want **>0** (the key signal)
- unparsed **38%** → want lower (format adherence)

---

## Your existing infra to clone from

| Project | What it gives |
|---|---|
| `~/dev/mgr_fine_tune` | **Working Unsloth DPO** (compiled `UnslothDPOTrainer`, `FastLanguageModel`, 4-bit). Ran on Llama-3.2-3B. → the DPO training pattern. |
| `~/dev/qwen3vl_recipe_finetune` | **Qwen3-VL-8B LoRA → merge → GGUF → Ollama** pipeline (text SFT on 90k recipes, on this 5090). → the Qwen3-VL LoRA + merge/convert scripts (`merge_lora_*.py`, `llama.cpp`). |
| Trainable model | `~/models/Qwen3-VL-8B-Instruct` (also `/u02/vllm/models/Qwen3-VL-8B-Instruct`). |

> Note: both existing projects are **text** training (SFT or text DPO). **Vision DPO has not been
> done on this box** — it's the genuinely new/risky part.

---

## Env: `unsloth` conda env

**Broken as of 2026-07-19:** `torch 2.6.0+cpu` while `torchvision`/`torchaudio` are `2.9.x+cu128`
(mismatch → `torch.cuda.is_available()` is False).

**Fix:**
```bash
~/miniconda3/envs/unsloth/bin/pip install "torch==2.9.1+cu128" \
  --index-url https://download.pytorch.org/whl/cu128
# verify:
~/miniconda3/envs/unsloth/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```
Env already has: unsloth 2026.1.2, unsloth_zoo, trl 0.24, peft 0.18, xformers, triton 3.5.

**Alternative env:** `ml` has working `torch 2.10.dev+cu128` + `peft`/`trl`/`qwen-vl-utils` already
added — but TRL 0.24 can't do Qwen-VL DPO (see gotchas), so `ml` is only useful for the text path
or eval.

---

## Two paths — decide at runtime

### 1. Text/sensor-only DPO — LOW RISK, do this first
The driving prompt already embeds the sensor readings as text. DPO the LLM **text-only**
(Unsloth `FastLanguageModel` on Qwen3-VL's language model, or a small Qwen text model), reusing
the `mgr_fine_tune` pattern. Captures the sanitize / emergency-stop / escape corrections (all
sensor+command driven). Sidesteps vision entirely. Proves the enforce-in-code distillation on
proven tooling.

### 2. Vision DPO — THE PRIZE, but frontier
Image + preference DPO on Qwen3-VL. Needs Unsloth to actually support **Qwen3-VL vision DPO**
(unproven — same class of risk as the TRL wall). If Unsloth vision-DPO doesn't work cleanly,
fallbacks: patch TRL's collator/`concatenated_forward` for Qwen-VL (`image_grid_thw` + flat
`pixel_values`), or try LLaMA-Factory (broad Qwen-VL + DPO support).

**Recommendation:** start with path 1 to bank a win, then attempt path 2 as the stretch.

---

## Known gotchas (learned the hard way, 2026-07-19)

- **`datasets` fork deadlock:** TRL `DPOConfig(dataset_num_proc=1)` spawns a `Pool(1)` that forks
  the CUDA-initialized parent → hard hang in `datasets.map` (`iflatmap_unordered`). Use
  `dataset_num_proc=None` (in-process, no fork). `1` ≠ in-process.
- **TRL 0.24 drops `image_grid_thw`:** its VLM collator/forward only handle padded `pixel_values`
  + `image_sizes`; Qwen3-VL needs flat `pixel_values` + `image_grid_thw` → vision forward crashes
  on `grid_thw=None`. This is why we deferred off TRL. No local VLM is TRL-native (Llama-3.2-Vision
  = Mllama, Phi-vision = custom — also unsupported).
- **Can't train the 35b drive model here:** only GGUF is local (not trainable); HF safetensors is a
  ~70GB OOM-risky download and 35B MoE-VLM DPO won't fit 32GB anyway. Train/POC substrate = Qwen3-VL-8B.

---

## Deployment loop (close it back to driving)

After training: **merge LoRA** (`qwen3vl_recipe_finetune/merge_lora_*.py`) → **convert to GGUF**
(`llama.cpp`) → add a **llama-swap** entry → the car drives with it (the drive pipeline talks to
llama-swap GGUF). Then re-run `obstacle_bench.py` + a live drive to validate.

---

## GPU coordination (for the multi-hour run)

`gpu-prep --profile training` frees ~27GB (stops llama-swap / comfyui / alltalk / immich-ml /
app containers, pins QM to cloud Sonnet, pauses timers). `gpu-restore` reverses it, fully.
**Gotcha:** QM's "pin to Sonnet" restart *fails* during `gpu-prep` (QM ends up down, not pinned)
but recovers cleanly when `gpu-restore` removes the drop-in — don't hand-restart QM mid-teardown.
</content>
