# AGENTS.md: parbench

Instructions for any coding agent (Claude Code, Codex, OpenCode, Pi, Antigravity, ...) or human teammate working in this repo. `CLAUDE.md` just imports this file. Nested `AGENTS.md` files in `src/parbench/`, `smoke/` and `docs/` add local rules.

## What this project is

An ASE course project: a benchmark and eval pipeline that measures how well **coding-agent harnesses and models handle k concurrent, possibly conflicting tasks** on one repo snapshot, with a focus on wasted effort (tokens, time, merge losses). Goals and scope are in `docs/Phase1_Proposal.md`.

The data comes from [CooperBench](https://github.com/cooperbench/CooperBench), pinned as a git submodule at `external/CooperBench` (commit `63b9d44`). We re-bundle its features into k-task groups. Our code is the Python package `parbench`.

## Vocabulary (ours vs. CooperBench's: don't mix them up)

| Our term | Meaning | CooperBench term |
|---|---|---|
| **task** | one feature with its own hidden tests | *feature* |
| **pool** | a set of compatible tasks: one repo at one base commit | *task* (`task1621`) |
| **bundle** | k tasks sampled from one pool, in a fixed seeded order | *pair* when k=2 |
| **run** | bundle x strategy x harness x model x repeat | n/a |
| **harness** | the agent CLI around the model (OpenCode, Pi, Claude Code, Codex, agy, Gemini CLI) | n/a |
| **S0 / S1 / S2 / S4** | isolated / one agent all tasks / parallel + merge / harness-native subagents | `solo` ~ S1, `coop` ~ S2 |

Metrics are defined in `docs/research/Task4_Metrics.md`, strategies in `docs/research/Task5_Strategies.md`.

## Ground rules

1. **The research docs in `docs/research/` are guidance, not a spec.** The user said so explicitly. Deviate when there is a reason, and say why.
2. **Ask the user before making real design decisions** (models, compute, strategies, metric definitions, anything that costs money). Don't pick silently. Use the question tool or leave a clearly marked `TODO(decision)`.
3. **Agents run only inside Docker containers.** The permission-bypass flags used by the adapters (`--dangerously-skip-permissions`, `bypassPermissions`, `--approval-mode yolo`, `-s danger-full-access`) are acceptable *only* in the throwaway containers that `src/parbench/sandbox.py` starts. Never run an agent CLI with those flags on the host. For host-side probing use `agy` with `--sandbox`, in a scratch directory.
4. **Never commit secrets or results.** API keys go in `.env` (git-ignored), never in configs. `results/` is git-ignored.
5. **Don't edit `external/CooperBench/`.** It is a pinned submodule. Copy code out (keeping the MIT attribution comment) instead. Port notes are in `docs/cooperbench_guide.md`.
6. **Mark what you did not verify.** If a fact about a CLI, model or dataset comes from docs and not from a run, say `UNVERIFIED`. Report failing tests or skipped steps plainly.
7. **Commit messages: a single line** that states the intention and what changed. No `Co-Authored-By` trailer and no AI attribution lines (user preference, see `~/.claude/CLAUDE.md`).
8. **Prefer small, readable changes.** No new dependencies without a reason: the package currently needs only `pyyaml`, and `scripts/check_endpoint.py` is stdlib-only on purpose.

## Repo map

```
AGENTS.md / CLAUDE.md      this file
pyproject.toml             package `parbench` (CLI entry point: parbench)
src/parbench/              the pipeline (see src/parbench/AGENTS.md)
prompts/*.md               prompt templates, ${placeholders}; edit these, not Python strings
configs/models.yaml        model registry (endpoints, prices, context)
configs/experiments/       experiment YAMLs (`parbench run <file>`)
docker/                    agent image = CooperBench pool image + agent CLIs
smoke/                     toy dataset + smoke tests (see smoke/AGENTS.md)
scripts/serve/             start Ollama / vLLM / llama.cpp / SLURM vLLM
scripts/check_endpoint.py  verify an endpoint (chat, tools, Anthropic, Responses, parallel)
docs/                      proposal + guides (see docs/AGENTS.md)
external/CooperBench/      pinned submodule with the dataset and gold patches
results/                   run outputs (git-ignored)
```

## Setup

```bash
git submodule update --init            # CooperBench dataset (~10 MB)
uv venv && uv pip install -e '.[dev]'  # installs the `parbench` command into .venv
open -a Docker                         # Docker Desktop must be running
```

Typical flow (see `docs/` for details):

```bash
parbench list-pools [--toy]                         # what's available
parbench bundles --k 3 --per-pool 2 > bundles.json  # inspect sampling
parbench build-toy                                  # toy pool base image (once)
parbench build-images --toy --harnesses opencode    # pool image + agent CLIs
parbench probe --toy --harness opencode --model qwen3.5-9b-ollama   # one agent, one prompt
parbench check-gold --pools toy_task/task1          # grader sanity check (no agents)
parbench run configs/experiments/<file>.yaml [--dry-run]
parbench report results/<experiment>
parbench cleanup                                    # remove stray containers
```

Set `PARBENCH_KEEP_CONTAINERS=1` to keep containers for debugging.

## How a run works

1. Plan: expand the config into runs. `results/<exp>/<run_id>/run.json` marks a finished run, so re-launching skips it.
2. Start containers from the pool's *agent image*. Scrub git history after the base commit (CooperBench images contain future upstream commits, which can leak the answer).
3. Run the strategy. S0 runs k isolated agents. S1 and S4 run one session with all k tasks. S2 runs k parallel agents and then merges their patches in three modes (naive, union, LLM resolver).
4. If an agent ends by asking a question, nudge it ("No human is available... Use your best judgement") by resuming the session, up to `max_nudges`. Nudges are counted and logged.
5. Collect each agent's diff vs. base ourselves (never trust an agent-written patch file).
6. Grade in fresh containers with the pool's own `/usr/local/bin/runner.sh`, once per task's hidden `tests.patch`, on the final tree and on each agent's own tree.
7. Write `run.json` with correctness, tokens, cost, time, conflicts, overlap, per-agent logs. `parbench report` turns these into `runs.csv` and `summary.md`.

## Current status (update this when it changes)

Written but **not yet validated end to end**: nothing has been run against real CooperBench images, and the adapters' event parsing for every CLI except agy is based on docs (`docs/harnesses.md`), not live output.

- [x] Dataset loading, bundling, k-feature grader, merge modes, strategies S0/S1/S2/S4, metrics, report
- [x] Adapters for OpenCode, Pi, Claude Code, Codex, agy, Gemini CLI (UNVERIFIED parsing except agy)
- [x] Toy dataset generator + image; serving guide and scripts
- [ ] Toy end-to-end run with a local model (`parbench probe`, then a toy experiment)
- [ ] `check-gold` on real CooperBench pools (arm64 images, ~28 GB for all 30)
- [ ] S2 `llm` merge mode port check; S3 (plan-then-schedule) not implemented
- [ ] Open decisions: which models for the real baselines, compute for them, repeats and budget

## Known pitfalls

- Local server defaults silently ruin runs: Ollama's default context is small (set `OLLAMA_CONTEXT_LENGTH`), thinking models can burn the whole token budget, and a wrong tool-call parser fails silently. Run `scripts/check_endpoint.py` first. See `docs/serving_models.md`.
- Ollama on Apple Silicon serves parallel requests one at a time here, so S2 timing on a Mac measures the queue, not the strategy. Use `max_parallel_runs: 1` and read time metrics with that in mind.
- Don't compare architectures: CooperBench's arm64 and amd64 images can differ in dependencies. Keep a comparison on one architecture.
- A graded feature passes only if `runner.sh` exits 0 and at least one test passed. Agent-written test files are removed from the patch before grading (they collide with the hidden tests).
