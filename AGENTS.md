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
3. **Agents run in Docker containers by default.** Host mode (no Docker) exists only for OpenCode and `agy`: set `host_harnesses: [opencode]` in an experiment config or pass `--host` to `probe`; `agy` always runs on the host because its login cannot be carried into a container. On the host the agent is NOT isolated by Docker; use it for toy runs, never with a permission-bypass flag.
   Container rule: The permission-bypass flags used by the adapters (`--dangerously-skip-permissions`, `bypassPermissions`, `--approval-mode yolo`, `-s danger-full-access`) are acceptable *only* in the throwaway containers that `src/parbench/sandbox.py` starts. Never run an agent CLI with those flags on the host. For host-side probing use `agy` with `--sandbox`, in a scratch directory.
4. **Never commit secrets or results.** API keys go in `.env` (git-ignored), never in configs. `results/` is git-ignored.
5. **Don't edit `external/CooperBench/`.** It is a pinned submodule. Copy code out (keeping the MIT attribution comment) instead. Port notes are in `docs/cooperbench_guide.md`.
6. **Mark what you did not verify.** If a fact about a CLI, model or dataset comes from docs and not from a run, say `UNVERIFIED`. Report failing tests or skipped steps plainly.
7. **`agy` (Antigravity) terms of service.** Google's FAQ allows `agy -p` for scripting, but says wrapping it in third-party tools is unsupported on consumer plans and can lead to suspension. The user was told (`docs/agy_quota.md`) and chose to keep using it on their own account at low concurrency. Don't add account rotation, and don't raise concurrency without asking.
8. **Commit messages: a single line** that states the intention and what changed. No `Co-Authored-By` trailer and no AI attribution lines (user preference, see `~/.claude/CLAUDE.md`).
9. **Prefer small, readable changes.** No new dependencies without a reason: the package currently needs only `pyyaml`, and `scripts/check_endpoint.py` is stdlib-only on purpose.

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
docs/                      proposal, guides, findings.md with measured numbers (see docs/AGENTS.md)
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

Partly validated (details and numbers in `docs/findings.md`): the toy pool runs end to end with OpenCode + a local 9B and with `agy`; grading is verified on go_chi task26 (real CooperBench, arm64). **No agent has run on a real CooperBench pool yet.** Parsing for OpenCode and `agy` is checked against live output; Pi, Claude Code, Codex and Gemini CLI parsing is still based on docs (`docs/harnesses.md`).

- [x] Dataset loading, bundling, k-feature grader, merge modes, strategies S0/S1/S2/S4, metrics, report
- [x] Adapters for OpenCode, Pi, Claude Code, Codex, agy, Gemini CLI (UNVERIFIED parsing except agy)
- [x] Toy dataset generator + image; serving guide and scripts
- [~] Toy end-to-end run: OpenCode + local 9B S0 passed; S1/S2 and the merge modes still running (`configs/experiments/toy_smoke.yaml`); agy + Gemini Flash S0/S1 passed (`toy_agy.yaml`, host mode)
- [~] `check-gold` on real CooperBench pools: go_chi task26 passes (4/4); the other 29 pools are not checked (arm64 ~28 GB for all 30)
- [ ] S2 `llm` merge mode port check; S3 (plan-then-schedule) not implemented
- [ ] Open decisions: which models for the real baselines, repeats and budget. The main OpenCode runs will happen on a different machine (see `docs/core_subset_plan.md`); this Mac is for validating the pipeline

## Known pitfalls

- **Web search can leak the answer, so `agy` runs use a restricted custom agent.** `agy` has a `search_web` tool that works headless and cannot be switched off with deny rules (tested); in the first `core_agy` runs Gemini searched for the upstream PR (`site:github.com/pallets/click/pull/2800`) and for `"cooperbench"`. Fix: `configs/agy_agents/parbench-clean.md` (no subagents) and `parbench-clean-sub.md` (S4) list every `agy` tool except the web/browser tools, `ask_question` and, in the first, the subagent tools. `AgyHarness.setup` copies them into `~/.gemini/config/agents/` (additive, only when changed) and the command passes `--agent`. Verified: `search_web` is unavailable and normal coding works. Only necessary tools are disabled; shell `curl` and similar are not blocked. `parbench audit-web results/<exp>` still lists any run with web calls (runs from before the fix are in `results/core_agy_web_contaminated/`, kept as evidence, not part of results). Names in an agent file must be real registry names (`agy` rejects unknown ones; `sed_file`, `wait_5_seconds` and a few others are not).
- `agy` + GPT-OSS 120B returns `503 No capacity available for model gpt-oss-120b-medium` (Google-side, retryable) under load; the nudge loop resumes the agent but spends a nudge each time.
- Never delete `parbench-host-*` temp directories (under `$TMPDIR`) while a host-mode job runs: they are live repo clones (this crashed a probe once). `parbench cleanup` only removes containers.
- Don't run extra probes against the model server while an experiment is running: Ollama serves one request at a time, so they slow the experiment and skew its timings.
- Docker Desktop defaults to little RAM (3.8 GB here); raise it to 10 GB or more before real pools.
- Local server defaults silently ruin runs: Ollama's default context is small (set `OLLAMA_CONTEXT_LENGTH`), thinking models can burn the whole token budget, and a wrong tool-call parser fails silently. Run `scripts/check_endpoint.py` first. See `docs/serving_models.md`.
- Ollama on Apple Silicon serves parallel requests one at a time here, so S2 timing on a Mac measures the queue, not the strategy. Use `max_parallel_runs: 1` and read time metrics with that in mind.
- Don't compare architectures: CooperBench's arm64 and amd64 images can differ in dependencies. Keep a comparison on one architecture.
- A graded feature passes only if `runner.sh` exits 0 and at least one test passed. Agent-written test files are removed from the patch before grading (they collide with the hidden tests).

## Project history: summary of the setup session (2026-11-06)

A condensed record of how the repo got here, so a teammate or agent can pick up without the chat. Numbers and sources are in `docs/findings.md`; plans in `docs/core_subset_plan.md`.

### What the user asked for, and decided

- Evaluate coding agents on **k concurrent, possibly conflicting tasks** (k up to 6) built from CooperBench "pools"; measure correctness, tokens, cost, wall-clock time, conflicts, wasted effort.
- Work was split across teammates. The teammate research notes (`docs/research/`) are **guidance, not a spec**. Ask before making design decisions.
- Harnesses to support: OpenCode, Pi, Claude Code, Codex CLI, Antigravity (`agy`) with Gemini. Pi has no native subagents, so no S4 for it; OpenCode has native subagents.
- Strategies first: S0 isolated, S1 one agent all tasks, S2 parallel + merge (naive / union / LLM resolver), S4 harness-native subagents; plus a worktree variant where the lead agent divides and merges (`S4@harness_native_worktrees`). Other candidates (S3 plan-then-schedule, S1b hand-off, S2b self-fix, prompt changes P1 to P3) are in `docs/research/Task5_Strategies.md`.
- Sandbox: agents run **inside Docker, built from the CooperBench pool image**, and may run the repo's existing tests. Headless runs must never block on a human: when an agent stops to ask, the runner resumes it with "No human is available... use your best judgement" (`prompts/nudge.md`, up to 2 times).
- Compute: local Ollama on the Mac for smoke tests; GPU machines and the IIIT Ada cluster later; frontier subscriptions. The **main OpenCode experiments will run on a different machine** (GPUs, a Qwen model); this Mac validates the pipeline. Guides must work on any NVIDIA GPU and on a Mac (`docs/serving_models.md`).
- Antigravity: the user chose to keep using `agy` (Gemini 3.8 Flash and GPT-OSS 120B, which has a separate quota) on their own account after being told about the terms-of-service caveat, and asked for more parallelism. `agy` runs on the host ("dirty" results are acceptable for the mid-term submission; logs can be checked later).
- Docker Desktop memory raised from 4 GB to 8 GB after stage A (restart job); the user allowed up to 8 to 9 GB.

### What was built

- Package `parbench` (`src/parbench/`): dataset loading and seeded k-bundles (including CooperBench's curated `core`/`flash_10`/`flash`/`lite` subsets), Docker sandbox plus host mode, six harness adapters, nudge loop, strategies S0/S1/S2/S4, merge modes, a k-feature grader reusing each image's `runner.sh`, metrics, report. Pinned CooperBench submodule (`external/CooperBench`, `63b9d44`). Toy dataset and smoke prompts in `smoke/`.
- Docs: `docs/cooperbench_guide.md`, `harnesses.md`, `serving_models.md`, `agy_quota.md`, `core_subset_plan.md`, `findings.md`; the `AGENTS.md` files.
- Teammate (MittalManas2005) added a no-Docker host-pool mode (`PARBENCH_HOST_POOLS`), OpenCode 1.x support, a vLLM Qwen2.5-7B model entry, a `small_model` prompt extra and a second `core` experiment arm. These were pulled in; the interaction with the `${repo}` prompt placeholder has not been checked.

### Where things stand (see "Current status" above for the checklist)

- Verified: the toy pool end to end with OpenCode + local `qwen3.5:9b` (S0, S1, S2 all pass; merge modes all graded; no real conflict exercised yet) and with `agy`; grading verified on 37 real CooperBench features across 5 `core` pools (dspy 8563, go_chi 26/27, click 2800, jinja 1559/1621) on arm64.
- First real agent result: `agy` + Gemini Flash, S0 on dspy 8563 pair f1+f4: 1 of 2 tasks passed, 27 minutes, about 7.4M input tokens (higher than the 0.8 to 2.1M per task we estimated).
- Experiments are launched per pool from `configs/experiments/core_agy_<pool>.yaml` (Gemini Flash) and `core_agy_gptoss_<pool>.yaml` (GPT-OSS 120B); all write to `results/core_agy` (git-ignored), one process per pool so pools run in parallel. Finished runs are skipped on relaunch. `parbench report results/core_agy` aggregates them.
- Not done: any agent run on a real pool with OpenCode; S3; S0 caching across bundles; Pi/Claude/Codex/Gemini-CLI adapters checked against live output; the conflict path of the LLM resolver; host vs Docker speed comparison; the `agy` quota cost of a real task.

### Gotchas that cost time this session

- OpenCode 2.x needs an explicit `models` map for custom providers. Thinking models on Ollama need `reasoning_effort: none`. `agy -p` needs its prompt attached to the flag, cannot log in inside a container, and cannot disable subagents. Details in `docs/findings.md`.
- Don't kill processes with a broad `pkill -f` pattern that can match the watcher's own command line, and don't delete host-mode temp clones while jobs run.
