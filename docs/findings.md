# Findings, measurements and sizing (live, 2026-11-06)

Things we learned by running, not by reading docs. Dated and sourced so they can be re-checked. Everything here was measured on one Apple Silicon Mac (M5, 24 GB), Docker Desktop (arm64, 3.8 GB RAM), unless stated. **Toy numbers only prove the plumbing; don't use them in the report.**

## 1. Verified behaviour

| Finding | How we saw it |
|---|---|
| **OpenCode 2.2.4 needs an explicit `models` map** for a custom OpenAI-compatible provider. Without it the run fails with `provider.no-route: Model unavailable: local/<model>`. Config: `providers.local.models.<key>.modelID` plus `limit`; select with `-m local/<key>`. | `parbench probe`, first run failed; fixed in `OpenCodeHarness.setup` |
| OpenCode in a container: events seen are `step_start`, `text`, `tool_use`, `step_finish{tokens{input,output,reasoning,cache{read,write}}}`; tool names `read`, `glob`, `shell`, `edit`. The JSON adapter parses real output. | probe + `toy_smoke` logs |
| **Thinking models are slow here.** `qwen3.5:9b` with thinking on took 5+ min per call (one call produced about 5,500 tokens). Setting `reasoning_effort: none` fixed it (a single-task probe then took 175 s). It's the only way that worked on Ollama's OpenAI endpoint. | Ollama log, probes |
| **Ollama serves one request at a time on this Mac** (MLX backend), whatever `OLLAMA_NUM_PARALLEL` says. Other jobs and probes queue behind a running agent, so parallel agents and S2 timings measure the queue. | Ollama log; `docs/serving_models.md` |
| **Ollama's `keep_alive` must be the number `-1`, not the string `"-1"`** (HTTP 400 otherwise). Fixed in `scripts/serve/ollama.sh`. | warm-up request |
| `agy -p` needs the prompt attached to the flag (`-p "…"`, after the other flags). `agy -p --output-format …` takes the flag as the prompt. | error message |
| **`agy` headless auto-denies tools** unless allowed: `--sandbox --mode accept-edits --settings '{"permissions":{"allow":["command(*)"]}}'` worked on the host (read_file, edit_file, run_command). `agy` has **no switch to turn subagents off**; our `--agent nosub` idea fails (`unknown agent "nosub"`), so subagents stay available and `subagent_calls` is logged (one probe used one). | probes |
| **`agy` login does not work inside a container** ("Authentication required"). The Gemini CLI token is a plain file (`~/.gemini/oauth_creds.json`), but `agy` has no credentials file; its login is probably in the macOS Keychain, which we did not read. So `agy` runs in **host mode** (`HostWorkspace`). | container probe |
| `agy` stream-json: `init`, `step_update{step_type, tool_info{name,parameters}, usage}`, `result{usage{input_tokens,output_tokens,thinking_tokens,cache_read_tokens}}`. Tool-argument names for file paths are not captured yet, so its "files read" metric is empty. | probes |
| **Grading works on a real CooperBench pool, arm64.** go_chi task26: tests alone fail, gold passes, `combined.patch` passes, for all 4 features. | `parbench check-gold` |
| **Toy grader:** tests alone fail, gold and `combined.patch` pass for all 6 features. | `parbench check-gold --toy` |
| Host mode isolates OpenCode: its config, data and cache go under a temp dir (`XDG_*`), and `~/.local/share/opencode` was untouched. Requests reached Ollama from localhost. Speed vs Docker is **not measured yet**. | probe + Ollama log |
| Building the agent image with four CLIs (opencode, pi, claude, codex) took about **16 minutes**, so build only the harness you use. | `parbench build-images` |

| **`agy` web search leaks the task source.** `search_web` completes headless, is not blockable via `permissions.deny` (`"search_web"` and `"search_web(*)"` both tested), and agents used it: Gemini searched `site:github.com/pallets/click/pull/2800` (the very PR) and `"cooperbench"`. `parbench audit-web <exp>` lists affected runs. First audit (7 runs so far): 2 Gemini runs had leak-looking queries (24 and 9), GPT-OSS used web search 1 to 23 times with none looking like a lookup of the upstream change, and the finished dspy S0 Gemini run used none. | stream-json logs |
| **Fix for the web leak:** custom agents in `configs/agy_agents/` (all tools except web/browser, `ask_question` and, for non-S4, subagent tools), installed to `~/.gemini/config/agents/`, run with `--agent`. Tested: `search_web` reported unavailable, coding unaffected. Pre-fix runs archived in `results/core_agy_web_contaminated/`. | test runs |
| **GPT-OSS 120B via `agy` hits Google capacity limits:** `503 UNAVAILABLE: No capacity available for model gpt-oss-120b-medium` (retryable) with 10 sessions in parallel. | stream-json logs |

## 2. Measurements (toy pool `textkit`, tiny tasks)

| Setup | Strategy | Wall time | Input / output tokens | Result |
|---|---|---|---|---|
| OpenCode + `qwen3.5:9b`, thinking off, local, Docker | single-task probe (slugify) | 175 s | n/a | correct |
| same | S0, bundle f3+f5 (k=2, 2 agents) | 938 s | 129K in | 2 of 2 pass |
| `agy` + `gemini-3.8-flash-low`, host | single-task probe (slugify) | 124 s | 318K in / 2.2K out | correct (also wrote a test, 1 subagent) |
| same | S0, f3+f5 | 299 s | 837K in / 6.0K out | 2 of 2 pass |
| same | S1, f3+f5 | 160 s | 410K in / 3.8K out | 2 of 2 pass |

Token counts are large because every step re-sends the context (~9K system prompt per turn for `agy`).

S1 and S2 for OpenCode, S2 and S4 for `agy`, and k=3 bundles were still running when this was written; update this table when `results/toy_smoke` and `results/toy_agy` finish (`parbench report <dir>`).

## 3. Sizing the full benchmark (computed from the dataset)

CooperBench at commit `63b9d44`: 30 pools, 199 features. Sessions per bundle = S0 k + S1 1 + S2 k + S4 1 (resolver sessions extra).

| k | all bundles | sessions, S0+S1+S2+S4 | sessions, S1+S2+S4 only |
|---|---|---|---|
| 2 | 652 | 3,912 | 2,608 |
| 3 | 1,409 | 11,272 | 7,045 |
| 4 | 2,219 | 22,190 | 13,314 |
| 6 | 2,344 | 32,816 | 18,752 |

- S0 only needs each feature once: **199 sessions** in total if cached across bundles (not implemented).
- A sampled design (1 bundle per pool, k=2,3,4,6, S1+S2+S4) is **577 sessions plus 199 S0**. With 2 per pool it is 1,079 plus 199.
- At 10 min per session (an assumption) the k=2 grid alone is about 650 hours back to back, so the full benchmark is infeasible on one local model. Curated subsets: `core` 10 pairs, `flash_10` 10, `flash` 50, `lite` 100 (`docs/core_subset_plan.md`).

## 4. Open measurements to take

- Host vs Docker speed for OpenCode on an idle model server.
- Per-session time and pass rate on real CooperBench pools (none run yet).
- S2 merge stage (naive/union/LLM) on a completed run.
- `agy` quota cost of one real task (`/usage` before and after, interactive only); see `docs/agy_quota.md`.
