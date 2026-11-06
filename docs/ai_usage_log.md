# AI usage log and verification checklist

Disclosure required by the course for substantial AI use: tools, prompts, outputs, and how outputs were verified or modified. Team **vam** (Vishesh Saraswat, Aviral Malhotra, Manas Mittal). The first section is a summary; the checklist at the end lists the files each member should read and check before submission.

## 1. Tools

| Tool | Used for |
|---|---|
| **Claude Code** (Claude Opus 5.5 and Sonnet 5.5) | Wrote most of the `parbench` pipeline, prompts, configs, the guides in `docs/`, the experiment launch scripts, and the report draft. Ran probes and experiments, diagnosed failures, and committed to git. |
| Claude Code research subagents | Read the CooperBench repository (`docs/cooperbench_guide.md`), the six agent CLIs (`docs/harnesses.md`), model-serving options (`docs/serving_models.md`) and Antigravity quota and terms (`docs/agy_quota.md`). Each doc marks facts as verified or UNVERIFIED. |
| AI agents as **experimental subjects** | OpenCode with Qwen models, Antigravity (`agy`) with Gemini 3.8 Flash and GPT-OSS 120B. Their outputs are the data being measured, not part of the project's code. |

The team's own pre-existing notes (`docs/research/`, `docs/Phase1_Proposal.md`) were written by the team before this session and treated as guidance, not a specification.

## 2. Who decided what

The AI proposed options and implemented them; **the team made the decisions**. Where a choice was a real fork the AI asked and the team answered. Decisions taken by the team in this session include:

- compute and models: local models for smoke tests, a separate GPU machine for the main OpenCode runs, Antigravity (Gemini, GPT-OSS) for hosted runs;
- harnesses to support: OpenCode, Pi, Claude Code, Codex CLI, Antigravity (Gemini);
- strategies for the first baseline: S0 isolated, S1 one agent, S2 parallel + merge, S4 harness-native subagents;
- sandbox: Docker per agent built from the CooperBench image, agents may run the project's tests;
- tasks: CooperBench's `core` subset first, k=2, then larger k;
- risk decisions: keep using Antigravity after being told about its terms, ask web search and other contaminating tools to be disabled, and accept lower-fidelity (host-mode, no-test) `agy` results;
- scope of the report (no individual contributions, short problems section).

## 3. Prompts and outputs (summary, not verbatim)

| # | What the team asked | What the AI produced |
|---|---|---|
| 1 | Describe the project, list the tasks (benchmarks, models, harnesses, metrics, strategies, setup); research CooperBench with a subagent; structure the repo; ask questions instead of deciding | Repo layout, `AGENTS.md`, `docs/cooperbench_guide.md`, clarifying questions to the team |
| 2 | Set up an evaluation environment for different harnesses and models; can Pi or OpenCode be used? simple prompts for OpenCode with a local model; more than two tasks per pool | The `parbench` package (dataset, sandbox, harness adapters, strategies, merge, grader, metrics, report), `smoke/` toy dataset and prompts |
| 3 | Run headless, allow tools, handle questions with "use your best judgement", sandbox | Nudge loop, Docker sandbox, host mode, custom `agy` agents |
| 4 | Serve models on any GPU or a Mac; set up Antigravity, Codex, Claude Code | `docs/serving_models.md`, `scripts/serve/`, `scripts/check_endpoint.py`, `docs/harnesses.md` |
| 5 | Run baselines in the background; use `agy` with Gemini and GPT-OSS; run more in parallel; core subset | Experiment configs in `configs/experiments/`, background launches, per-pool processes |
| 6 | "Please just disable web search, and any other tools that may contaminate our evals" | `configs/agy_agents/`, `parbench audit-web`, archive of contaminated runs |
| 7 | Document findings, push to GitHub, summarise the chat in `AGENTS.md`, commit results | `docs/findings.md`, `AGENTS.md` history section, tracked `results/` with redaction |
| 8 | Draft the mid-submission report, shorten problems, redraw the figure | `report/main.tex`, `report/make_tables.py` |

## 4. How outputs were verified

- **Grader checked against ground truth:** for 41 real CooperBench features in six pools and for the 6 toy features, tests fail on the base, the gold patch passes, and CooperBench's combined patch passes (`parbench check-gold`).
- **Dry runs** of every experiment plan before launching; syntax checks after each edit.
- **Live probes** of OpenCode and `agy` against the real tools to correct parsers and configs (several first guesses were wrong and were fixed, see `docs/findings.md`).
- **Log inspection:** web-use audit (`parbench audit-web`), error and validity checks, scanning logs for secrets before they were committed (environment dumps and tokens were found and redacted).
- **Items corrected after the AI's first attempt:** OpenCode provider config, Ollama `keep_alive`, `agy` flag order, a redaction that broke JSON, the retry logic for service errors, and the run-validity flag.
- **Not independently verified by AI-free means:** parsers for Pi, Claude Code, Codex and Gemini CLI (documentation only); the S2 LLM-resolver on a real conflict; absolute pass rates.

## 5. Files to read and check (manual verification)

Tick each box when read. "Check" says what to look for.

| Done | File | Check |
|---|---|---|
| [ ] | `src/parbench/grader.py` | A task passes only if the runner exits 0 and at least one test passed; agent-written test files are removed before grading; each task graded from a clean reset |
| [ ] | `src/parbench/strategies.py` | S0, S1, S2, S4 do what the report says (one agent per task or per bundle; S2 merges afterwards; S4 enables subagents) |
| [ ] | `src/parbench/merge.py` | The three merge modes, the pairwise conflict rate, and the overlap count are computed as described |
| [ ] | `src/parbench/agent_runner.py` | Nudge rules, retry-through-service-errors, token accumulation, and the `infra_failed` flag |
| [ ] | `src/parbench/runner.py` | Metrics in `build_record` (pass rate, retention, lost in merge, wasted tokens, parallelism) and the `valid` flag |
| [ ] | `src/parbench/sandbox.py` | History scrub after the base commit, diff collection, host mode, environment allow-list |
| [ ] | `src/parbench/dataset.py` | Bundle sampling and `core`-subset handling (k>2 extends each pair from the same pool) |
| [ ] | `src/parbench/harnesses/cli_agents.py` | Per-harness token conventions (cached tokens included in input), the `agy` command and agent selection |
| [ ] | `prompts/*.md` | The exact text agents receive (preamble, single and multi-task prompts, nudge, resolver) |
| [ ] | `configs/agy_agents/*.md` | Which tools are disabled (web, browser, `ask_question`, subagents unless S4) |
| [ ] | `configs/experiments/core_agy_*.yaml`, `configs/models.yaml` | Settings behind every reported number (pools, k, seeds, models, timeouts) |
| [ ] | `docs/findings.md` | Each claim has a source in the logs |
| [ ] | `report/main.tex` and `results/core_agy/*/run.json` | Every number in the report's tables matches the run records; open two or three runs and compare with their raw logs under `agents/` |

Record in the box column who checked what, e.g. initials, before submitting.
