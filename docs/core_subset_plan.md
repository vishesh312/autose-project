# Plan: OpenCode on the CooperBench `core` subset

Status as of 2026-11-06: **not ready to launch yet**; see the checklist. The main OpenCode experiments will run on **another machine** (not this Mac), so the Mac is for validating the pipeline and the other machine is where the checklist below must be satisfied; see "Running on another machine". This page says what `core` is, why we pick it over `flash_10`, what is already verified, what still blocks a run, and the exact commands once it is unblocked.

## Which subset

CooperBench ships curated subsets in `external/CooperBench/dataset/subsets/`: `core` (10 pairs), `flash_10` (10 pairs), `flash` (50), `lite` (100). Both 10-pair sets have the same number of pairs and pools, so "smaller" comes down to image weight and diversity:

| | `core` | `flash_10` |
|---|---|---|
| pairs / distinct pools | 10 / 10 | 10 / 10 |
| repos | 9, four languages (Python, Go, TypeScript, Rust) | 9 |
| heaviest images (arm64, from `docs/cooperbench_guide.md`, approximate) | outlines 1655 (~4 GB), typst (~2.4 GB) | outlines 1655 (~4 GB), HF-datasets 6252 (~3.8 GB), typst (~2.4 GB) |
| sampling | stratified diversity sampling, proportional repo allocation with a language floor, seed 42; built so its pass rate roughly tracks the full dataset's | CooperBench's own curated 10 |

**Pick `core`:** lighter (no HF-datasets image), covers all four languages, and its design goal is to be representative. Docker Hub returned no per-image sizes when I checked, so the sizes above come from the earlier guide, not a fresh measurement.

`core` pools and pairs:

| Pool | Pair (features) |
|---|---|
| dottxt_ai_outlines / task1655 | 1, 3 |
| dspy / task8563 | 1, 4 |
| go_chi / task27 | 3, 4 |
| llama_index / task17244 | 5, 6 |
| openai_tiktoken / task0 | 4, 8 |
| pallets_click / task2800 | 1, 4 |
| pallets_jinja / task1559 | 5, 8 |
| pallets_jinja / task1621 | 6, 10 |
| react_hook_form / task153 | 2, 6 |
| typst / task6554 | 2, 6 |

It is **k=2 only**. For k>2 our runner keeps each curated pair and adds features from the same pool (seeded). Those bundles are our design, not CooperBench's.

## Readiness checklist

| # | Item | State |
|---|---|---|
| 1 | Grader works on a real CooperBench pool on arm64 (tests fail alone, gold passes, combined passes) | **Done for go_chi task26** (4/4 features). Not yet for the other 9 `core` pools, or go_chi task27 |
| 2 | Pipeline end to end with OpenCode in Docker | **Partly.** Toy: S0 passed (2 of 2 tasks). S1 running. **S2 and the merge stage (naive/union/LLM resolver) have not completed a run yet** |
| 3 | Docker Desktop memory | **Blocker.** 3.8 GB now. typst (Rust) and HF/outlines builds need roughly 10 GB or more. Needs you: Docker Desktop, Settings, Resources. The Mac has 24 GB and the 9B model takes about 8 GB |
| 4 | Pool images pulled (9 more pools) | Not done. About 10 GB compressed in total, mostly outlines and typst. Disk is fine (about 550 GB free) |
| 5 | Agent images (pool image + OpenCode) | Built for the toy pool only. `parbench build-images --harnesses opencode` has not been run on real pools, and **not on the Alpine-based go_chi image** (OpenCode musl binary and Node install there are unverified) |
| 6 | Model decision | **Needs you.** See below |
| 7 | OpenCode adapter parsing | Verified live against OpenCode 2.2.4 (tokens, tool calls, resume not yet exercised). Subagents are off in S0/S1/S2 |
| 8 | Run time is acceptable | **Doubtful on the local 9B.** See below |

### Model and time

The toy S0 run (2 tiny tasks, local `qwen3.5:9b`, thinking off, Ollama also serving other jobs) took 938 s of wall time. Real CooperBench features are much larger than the toy ones. Treat these as rough estimates:

- Sessions for `core`, k=2: S0 20 (each feature once) + S1 10 + S2 20 = **50 sessions**, plus LLM-resolver sessions in S2 and 10 more for S4.
- At 15 to 30+ minutes per session on this setup, that is **roughly 12 to 25+ hours**, one session at a time, because Ollama on this Mac serves requests one at a time. S2 timings would only measure that queue.
- CooperBench's own result for a 30B open model is about half of GPT-5's success rate (see `docs/research/Task2_Models_Harnesses.md`), so a 9B may pass few of these. We would learn about the pipeline but little about the strategies.

Options (your decision):
1. **Local 9B, a reduced `core`** (about 4 small pools: go_chi, jinja x2, click, dspy). About 20 sessions, still many hours.
2. **A bigger local model on a GPU box** (see `docs/serving_models.md`): batching makes S2 meaningful.
3. **A hosted open model through OpenRouter** with OpenCode: fast, parallel, cents per task. Needs an API key and a budget.
4. **`agy` + Gemini Flash** (host mode only): see `docs/agy_quota.md` for the quota and terms-of-service caveats.

## Running on another machine

What a fresh machine needs (Linux with an NVIDIA GPU, or another Mac):

1. `git clone --recurse-submodules <repo>` (or `git submodule update --init`), then `uv venv && uv pip install -e '.[dev]'`.
2. Docker, with enough memory (Docker Desktop: Settings, Resources; native Linux Docker uses host RAM). Agents run in containers; on Linux the runner adds `--add-host host.docker.internal:host-gateway` itself, so `base_url: http://host.docker.internal:<port>/v1` in `configs/models.yaml` keeps working. The model server must listen on `0.0.0.0` (the `scripts/serve/` scripts do).
3. A model server: `scripts/serve/vllm.sh` (NVIDIA), `llamacpp.sh`, `ollama.sh`, or `slurm_vllm.sbatch`. Pick the right entry in `configs/models.yaml` (host and port) or add one. Run `python scripts/check_endpoint.py --base-url ... --model ... --parallel N` first; it catches a wrong tool-call parser and silent context truncation. Guide: `docs/serving_models.md`.
4. Then steps 2 to 4 below (check-gold, build agent images, run). Pools are pulled from Docker Hub as `akhatua/cooperbench-*`.

Things that differ from the Mac:
- **Architecture:** an x86-64 Linux box pulls the **amd64** images, which can have different dependencies from arm64 (e.g. outlines 1371 is 4.55 GB on amd64 vs 0.54 GB on arm64). **Do not mix architectures within one comparison**; record the architecture with the results (`run.json` has `arch`).
- **Concurrency:** a vLLM/GPU server batches requests, so S2 and S4 timings become meaningful there. Record `--max-num-seqs`, GPU, quantisation and context length (see `docs/serving_models.md`).
- **Host mode** (`host_harnesses`, `agy`) is Mac-oriented and optional; Linux runs should use Docker.
- **Not yet tested on Linux:** the agent-image install script on Debian/Alpine amd64 and the `--add-host` path. Run one `parbench probe` on the new machine before a full run.

## Commands once unblocked

```bash
# 0. Docker Desktop: set memory to >= 10 GB, restart Docker.
# 1. model server (Ollama example), from scripts/serve/
PORT=11435 PARALLEL=2 CTX=65536 VALIDATE=0 scripts/serve/ollama.sh qwen3.5:9b

# 2. validate grading on every core pool (pulls images; ~10 GB)
parbench check-gold --pools dottxt_ai_outlines_task/task1655 dspy_task/task8563 go_chi_task/task27 \
  llama_index_task/task17244 openai_tiktoken_task/task0 pallets_click_task/task2800 \
  pallets_jinja_task/task1559 pallets_jinja_task/task1621 react_hook_form_task/task153 typst_task/task6554

# 3. agent images: OpenCode only (one image per pool)
parbench build-images --pools <same list> --harnesses opencode

# 4. dry run, then run in the background
parbench run configs/experiments/core_opencode.yaml --dry-run
nohup parbench run configs/experiments/core_opencode.yaml > /tmp/core.log 2>&1 &
parbench report results/core_opencode
```

`configs/experiments/core_opencode.yaml` is a **DRAFT**: model, repeats, strategies and which pools to include need the team's OK.

## Things we know are missing

- S0 results are not cached across bundles. For `core` k=2 it does not matter (each feature appears once), but it will for larger designs.
- S3 (plan, then schedule) is not implemented.
- Grading probably needs network access (`pip install` inside `runner.sh`); unverified offline.
- The paper's own LLM-resolver prompt is not ported. Our resolver is the same OpenCode agent, with a prompt in `prompts/resolver.md`.
