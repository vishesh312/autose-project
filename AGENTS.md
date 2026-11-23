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
3. **Big runs use the no-Docker host-pool mode** (user decision 2026-11-23: "do without docker"; the GPU box has no Docker either). Set `PARBENCH_HOST_POOLS=<root>` and prepare pools once with `scripts/host_setup_pools.sh <pool>...` (Mac pools live at `~/parbench_pools`). Agents and grading then run on the host; only OpenCode and `agy` are host-capable. Docker containers remain supported but are no longer the main path.
   On the host, `hide_gold` (default on) blocks agents from reading the dataset, the parbench checkout and other workspaces (seatbelt on Mac, Landlock on Linux). `agy` cannot be guarded this way, so run `parbench audit-leak results/<exp>` on every `agy` experiment. `sandbox: on` (default off) additionally limits network to the model endpoint and writes to the workspace; see `docs/sandboxing.md` and run `scripts/sandbox_selftest.sh` on a new host.
   Container rule: The permission-bypass flags used by the adapters (`--dangerously-skip-permissions`, `bypassPermissions`, `--approval-mode yolo`, `-s danger-full-access`) are acceptable *only* in the throwaway containers that `src/parbench/sandbox.py` starts. Never run an agent CLI with those flags on the host. For host-side probing use `agy` with `--sandbox`, in a scratch directory.
4. **Never commit secrets.** API keys go in `.env` (git-ignored), never in configs. `results/` IS tracked (user decision before the mid-term): scan new logs for tokens/env dumps before committing them, and restore tracked `results/*/bundles.json`/`experiment.json` that a `--dry-run` rewrites.
10. **Measure what the harness does by default.** (User, 2026-11-23.) Pass no sampling or thinking parameters (no temperature, top_p, `reasoning_effort`); the server applies the model card's `generation_config.json`. Output limits are as high as the model/server allow. Disabling tools (web, `ask_question`, subagents outside S4) must not change the system prompt: verify with a request log after any harness/config change (`docs/readiness.md` lists the remaining known diffs).
11. **Tokens are the main result, so measure them from the source.** OpenAI-compatible models go through the token meter (`src/parbench/meter.py`), and reports use its counts (`token_source: proxy`). For `agy`, sum per-step usage (`result.usage` is a running total for the conversation). Definitions: `docs/metrics_tokens.md`. Any parser change needs a check against a proxy log or raw stream.
5. **Don't edit `external/CooperBench/`.** It is a pinned submodule. Copy code out (keeping the MIT attribution comment) instead. Port notes are in `docs/cooperbench_guide.md`.
6. **Mark what you did not verify.** If a fact about a CLI, model or dataset comes from docs and not from a run, say `UNVERIFIED`. Report failing tests or skipped steps plainly.
7. **`agy` (Antigravity) terms of service.** Google's FAQ allows `agy -p` for scripting, but says wrapping it in third-party tools is unsupported on consumer plans and can lead to suspension. The user was told (`docs/agy_quota.md`) and chose to keep using it at low concurrency. On 2026-11-23 the user explicitly asked for cycling across their own 3 accounts (`configs/agy_accounts.yaml`, `src/parbench/agy_accounts.py`), knowing the FAQ calls automated account rotation unsupported and that it can lead to suspension. Don't add more accounts or raise concurrency without asking.
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
results/                   run outputs (tracked; redact before committing)
configs/agy_accounts.yaml  Antigravity account profiles for cycling (login: scripts/agy_login_account.sh N)
scripts/host_setup_pools.sh  prepare no-Docker pools (repo at base commit + venv)
scripts/sandbox_selftest.sh  check network/write/gold isolation on a host
scripts/recheck_tokens.py  recompute agy tokens of old runs (double-count fix)
tests/                     pytest unit tests (no Docker, no models)
```

Start with `docs/readiness.md` (what is ready, decisions with rationale, open items) and `docs/runbook_qwen_vllm.md` (GPU box).

## Setup

```bash
git submodule update --init            # CooperBench dataset (~10 MB)
uv venv && uv pip install -e '.[dev]'  # installs the `parbench` command into .venv
export PARBENCH_HOST_POOLS=~/parbench_pools && scripts/host_setup_pools.sh pallets_click_task/task2800   # no-Docker pools
pytest -q tests                        # unit tests
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
parbench cleanup [--host-temp HOURS]                # stray containers; stale host clones (refuses while a job runs)
parbench audit-web results/<exp>                    # web tool use
parbench audit-leak results/<exp>                   # reads of gold/tests/dataset, shell network attempts
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

As of 2026-11-23 (details in `docs/readiness.md`): mid-term results exist for `agy` (Gemini 3.8 Flash complete, GPT-OSS partial) and OpenCode + Qwen2.5-7B on 5 `core` pools, k=2. Before big runs, four audits fixed: orchestration bugs (S2 llm merge discarded unstaged resolutions; `${repo}` not substituted in nudge/resolver prompts; test files counted as conflicts; bundle order depended on the pool list), token accounting (agy double counted resumed attempts: GPT-OSS +79–123%; OpenCode missed child sessions and title calls), model params (all arbitrary constants removed), and host isolation. Mid-term token numbers must be recomputed with `scripts/recheck_tokens.py`.

- [x] Pipeline: dataset/bundling, strategies S0/S1/S2/S4, merge modes, grader, metrics, report; 33 unit tests
- [x] No-Docker host pools on the Mac: gold checks pass for click 2800, jinja 1559/1621, go_chi 26/27 (dspy 8563 pending setup)
- [x] OpenCode (1.19.5 and 2.2.4) and `agy` parsers checked against live output and a token proxy; Pi, Claude Code, Codex, Gemini CLI still UNVERIFIED
- [x] `agy` 3-account cycling (accounts 2 and 3 need `scripts/agy_login_account.sh N` by the user)
- [ ] Qwen3.8-27B on vLLM not yet run (GPU box: follow `docs/runbook_qwen_vllm.md`); `qwen27b_core_DRAFT.yaml` has open `TODO(decision)`s
- [ ] Sandbox `on` mode not yet used with a real run; Landlock path UNVERIFIED on Linux
- [ ] S3 (plan-then-schedule) not implemented (planner rules in `s3_planner_rules.md`)

## Known pitfalls

- **Web search can leak the answer, so `agy` runs use a restricted custom agent.** `agy` has a `search_web` tool that works headless and cannot be switched off with deny rules (tested); in the first `core_agy` runs Gemini searched for the upstream PR (`site:github.com/pallets/click/pull/2800`) and for `"cooperbench"`. Fix: `configs/agy_agents/parbench-clean.md` (no subagents) and `parbench-clean-sub.md` (S4) list every `agy` tool except the web/browser tools, `ask_question` and, in the first, the subagent tools. `AgyHarness.setup` copies them into `~/.gemini/config/agents/` (additive, only when changed) and the command passes `--agent`. Verified: `search_web` is unavailable and normal coding works. Only necessary tools are disabled; shell `curl` and similar are not blocked. `parbench audit-web results/<exp>` still lists any run with web calls (runs from before the fix are in `results/core_agy_web_contaminated/`, kept as evidence, not part of results). Names in an agent file must be real registry names (`agy` rejects unknown ones; `sed_file`, `wait_5_seconds` and a few others are not).
- `agy` + GPT-OSS 120B returns `503 No capacity available for model gpt-oss-120b-medium` (Google-side, retryable) under load; the runner waits and resumes without spending a nudge, and does NOT switch accounts (capacity is global). Per-account quota errors switch to the next account (fresh session on the partly edited repo).
- `agy --agent` replaces part of the default system prompt; the custom agents carry the default sections verbatim. Remaining diffs (section order, tool-derived text) are listed in `docs/readiness.md`. Never leave extra agent files in `~/.gemini/config/agents/`: S4 offers them as subagents.
- OpenCode in host mode used to load the host user's `~/.claude` skills and `CLAUDE.md` into its system prompt; the adapter now disables that. Re-check after OpenCode upgrades.
- vLLM reports cached tokens only with `--enable-prompt-tokens-details`.
- Never delete `parbench-host-*` temp directories (under `$TMPDIR`) by hand while a host-mode job runs: they are live repo clones (this crashed a probe once). Use `parbench cleanup --host-temp HOURS`, which refuses while a job runs.
- Don't run extra probes against the model server while an experiment is running: Ollama serves one request at a time, so they slow the experiment and skew its timings.
- Docker Desktop on the Mac stopped starting on 2026-11-23; use host pools. If you use Docker, give it 10 GB or more of RAM.
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
- Experiments are launched per pool from `configs/experiments/core_agy_<pool>.yaml` (Gemini Flash) and `core_agy_gptoss_<pool>.yaml` (GPT-OSS 120B); all write to `results/core_agy`, one process per pool so pools run in parallel. Finished runs are skipped on relaunch. `parbench report results/core_agy` aggregates them.
- Not done: any agent run on a real pool with OpenCode; S3; S0 caching across bundles; Pi/Claude/Codex/Gemini-CLI adapters checked against live output; the conflict path of the LLM resolver; host vs Docker speed comparison; the `agy` quota cost of a real task.

### Gotchas that cost time this session

- OpenCode 2.x needs an explicit `models` map for custom providers. Thinking models on Ollama are slow (we used `reasoning_effort: none` then; since 2026-11-23 no such parameter is passed, see rule 10). `agy -p` needs its prompt attached to the flag, cannot log in inside a container, and cannot disable subagents. Details in `docs/findings.md`.
- Don't kill processes with a broad `pkill -f` pattern that can match the watcher's own command line, and don't delete host-mode temp clones while jobs run.

## Project history: readiness session for big runs (2026-11-23)

User requests and decisions: prepare big runs with Qwen (vLLM + OpenCode, GPU box) and `agy`; cycle through the user's 3 Antigravity accounts; harnesses in their default behaviour except internet tools; sandbox if feasible; then "do without docker"; tokens must be measured correctly ("otherwise there's no point of this study"); no arbitrary model parameters, output limits as high as possible; the system prompt must not change when tools are disabled; minimal code for the user to review. Independent agents audited and fixed each area; results, decisions with rationale and open items are in `docs/readiness.md`. Key outcomes: `agy` token double counting fixed (old GPT-OSS numbers inflated), token meter added for OpenAI-compatible models, 10 orchestration bugs fixed, host-pool mode completed on macOS with gold hiding, `agy` multi-account profiles via per-process `HOME`.
