# Readiness for big runs (2026-11-23)

Seven independent agents each checked or fixed one area: Antigravity accounts, OpenCode with vLLM, sandboxing, an orchestration audit, token measurement, model defaults and system prompts, and the remaining gaps. Everything is merged into `main`; `pytest tests/` (33 tests) and dry runs of `toy_agy`, `toy_smoke`, `qwen27b_core_DRAFT` and `core_agy_click` pass. **Docker is not used** (user decision): agents and grading run on the host from prepared host pools (`PARBENCH_HOST_POOLS`).

## Verdict

| Path | Ready? | Blocking items |
|---|---|---|
| `agy` (Gemini, GPT-OSS) on the Mac, no Docker | **Yes, after the to-dos** | Log in accounts 2 and 3. A probe on the click host pool worked. `agy` file tools can read the gold patches (no read guard possible): run `parbench audit-leak` on every `agy` experiment. |
| OpenCode + Qwen3.8-27B on vLLM (GPU box) | **Ready for the one-bundle trial**, not yet the big run | Follow `docs/runbook_qwen_vllm.md` (start vLLM with `--enable-prompt-tokens-details`). The 27B model has not been run; the tool parser and whether 262144 context fits can only be checked on the box. Run `scripts/sandbox_selftest.sh` there (Landlock is UNVERIFIED on Linux). |
| Token measurement | **Yes** | OpenCode: metering proxy matched every request to the token. `agy`: per-step sums; old results need `scripts/recheck_tokens.py`. |
| Host pools on the Mac | **Yes (6 of 6)** | Gold checks pass on the host for dspy 8563, click 2800, jinja 1559/1621, go_chi 26/27. |
| Sandbox network/write limits | **Built, opt-in (`sandbox: off`)** | Gold hiding (`hide_gold`) is on by default regardless. |
| Orchestration | **Yes** | 10 bugs fixed (below). |

## Decisions and rationale

| Decision | Rationale |
|---|---|
| `agy` accounts are chosen per process with `HOME=<profile>`, each profile holding its own keychain | The `agy` login is a macOS keychain item found through `$HOME`. Per-process selection lets parallel jobs use different accounts without touching the main login. |
| Switch accounts only on the per-account quota error (`429` / "Individual quota reached"); on `503 No capacity`, wait | Capacity errors are Google-wide, so switching would not help. |
| Fill accounts in order; mark an exhausted account until its "Resets in" time, in a file shared across processes | Keeps per-account concurrency the same as today. All per-pool processes see the mark. |
| After a switch the agent starts a fresh session on the partly edited repo | Conversations live inside each profile. Resuming across profiles is untested. |
| Web tools are removed in both harnesses; every other default tool stays | Web search leaked upstream PRs before. Other tools are part of the harness's normal behaviour. |
| OpenCode 2.x: Code Mode (`execute`) off in all strategies | It hides nested tool calls from logs and does not exist in 1.x, so S1 and S4 then differ only in subagents. Side effect: the system prompt loses its Code Mode tool catalog (see below). |
| No sampling or thinking parameters anywhere (temperature, top_p, `reasoning_effort` removed from `models.yaml` and `OpenCodeHarness`) | User: model-card defaults. vLLM applies `generation_config.json` (`--generation-config auto` is its default in 0.8.5 and 0.33); Ollama its Modelfile. OpenCode 1.19.5 has no Qwen sampling defaults and sends `temperature` only for `temperature: true` models; 2.2.4 sent none (proxy) |
| Thinking on for Qwen3.x (`THINK=0` and Ollama `reasoning_effort: none` dropped) | Model-card default. Costs more output tokens and time per turn (on the Mac 9B: minutes per call) |
| Output limit = the whole context (`max_output` unset; OpenCode `limit.output = limit.input = context`, 1.x cap lifted with `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX`) | User: as high as possible. vLLM 0.33 caps `max_tokens` at context minus prompt instead of failing; 2.2.4 computes context minus estimated prompt itself (proxy). Requests seen: 1.19.5 `max_tokens: 32768` = context; 2.2.4 `max_completion_tokens` ≈ context − prompt |
| Qwen2.5-7B keeps `max_output: 8192` (was 4096) | Its model-card generation limit; vLLM 0.8.5 rejects prompt + `max_tokens` > context, so the whole context cannot be the output limit there |
| Qwen3.8-27B context 262144 (was 65536) | Native length; vLLM refuses to start if it doesn't fit and says what does (runbook) |
| OpenCode: `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT`/`_SKILLS` set | In host mode OpenCode put the host user's `~/.claude/CLAUDE.md` and `~/.claude/skills` into the system prompt; with the flags it matches a clean machine |
| System prompt = harness default | OpenCode 1.19.5: byte-identical to the default config on a clean `HOME` (S0-S2 and S4; proxy, `qwen3.5:2b`). 2.2.4: identical except the Code Mode catalog of the denied `execute` tool. `agy`: custom agents now carry the 5 dropped default sections verbatim. Remaining differences: section order, trailing newlines, and text agy derives from the tool set (`messaging`, `subagents`, built-in `skills` list) |
| Sandbox: Docker `--internal` network + `socat` forwarder to the model port only | Needs no iptables, root or image change, and the model URL stays the same. |
| Sandbox: Landlock on the GPU box | Works without root, unlike bubblewrap on Ubuntu 24.04 (AppArmor) and firejail (setuid). It blocks writes outside the workspace and, on ABI ≥4, TCP except the model port. |
| Sandbox: rely on `agy --sandbox` on the Mac | `agy` needs Google's API, so wrapping it adds little. Its seatbelt already blocks network and `$HOME` writes per shell command. |
| S2 conflicts are now measured on patches without agent-written test files | CooperBench does the same; test-only clashes made naive merges drop real work. **Changes conflict numbers vs the mid-term report.** |
| Token meter (reverse proxy) for OpenAI-compatible models; reports use its counts | The server's own `usage` is ground truth and includes subagent child sessions, title and compaction calls that OpenCode's JSON omits (16% of input in a subagent probe). The proxy never changes requests and never estimates missing usage. |
| `agy` tokens = sum of per-step usage, plus each subagent's transcript | `result.usage` is a running total for the conversation (checked on all 223 logged attempts), so adding it per attempt double counted every resume. |
| Tokens of failed/retried attempts are counted, and also reported separately | They are real cost; separating them keeps strategy comparisons readable. |
| `hide_gold` on by default in host mode, hiding the dataset, the whole checkout and other clones | Host mode is now the only path; results of other runs and grading clones leak answers too. |
| Relaunch retries invalid (quota/capacity/server-down) runs | Otherwise those bundles silently drop out of the comparison. |
| Wall-clock = time any agent ran (+ S2 merge), excluding setup and grading | The old measure included setup for S0 but not S1/S4. |
| Bundles are seeded per pool | Before, a pool's task order depended on which other pools a config listed, so harnesses ran different bundles. |

## Bugs fixed that affect earlier numbers

1. **S2 LLM merge:** a resolver that removed conflict markers without `git add` was counted as failed and its work thrown away (seen in the go_chi 27 S2 run). Earlier S2 `llm` numbers with conflicts are suspect.
2. **Prompts:** the nudge, resolver and S4-worktree prompts sent a literal `${repo}`.

The other fixes are robustness fixes: Ctrl-C handling, container cleanup on setup failure, atomic `run.json`, stale-log handling, all `+extra` snippets applied, the resolver's harness files kept out of the diff, and graded-once caching.

## To-dos for the user

1. Run `scripts/agy_login_account.sh 2` and then `3`, signing in with the second and third Google accounts.
2. Decide whether S4 on `agy` gets the default `swarm` tool (recommended: yes, it is a default tool).
3. Teammate on the GPU box: follow the runbook, run `scripts/sandbox_selftest.sh http://localhost:8000/v1/models`, then the `qwen27b_click` trial.
4. Fill the `TODO(decision)` lines in `configs/experiments/qwen27b_core_DRAFT.yaml`: k, bundles per pool, repeats and prompt extras.
5. Recompute mid-term token numbers with `scripts/recheck_tokens.py` before reusing them (GPT-OSS was inflated by 79–123%).

## Known gaps

Fixed 2026-11-23:
- Token accounting: OpenCode tokens come from a metering proxy (includes child sessions and title calls); agy double counting of resumed attempts fixed (`docs/metrics_tokens.md`, `scripts/recheck_tokens.py`).
- Gold patches / hidden tests: host-mode agents (OpenCode, host pools) now run under a read guard (seatbelt on the
  Mac, tested with a real OpenCode probe; Landlock on Linux, UNVERIFIED) that hides the dataset, the parbench
  checkout and other workspaces (`hide_gold`, default on; docs/sandboxing.md). **agy cannot be guarded** (nested
  sandbox-exec fails); run `parbench audit-leak results/<exp>` on agy experiments.
- Invalid (quota/capacity/server-down) runs are retried on relaunch (`retry_invalid`, default on); old outputs in `_prev/`.
- Model server down / 5xx counts as infra (retry with backoff, then `infra_failed`); context overflow stays valid
  and is recorded as `agents[].context_exceeded`.
- Every prompt sent is logged (`agents/<id>/attemptN.prompt.md`).
- Wall-clock time is defined the same for all strategies (docs/research/Task4_Metrics.md).
- `agy` agent-file install uses a unique temp name per call (threads shared one before).
- Stale clones: `parbench cleanup --host-temp HOURS` (refuses while a parbench job runs; skips live owners).

Still open:
- agy can still read gold patches through its file tools (no read guard possible); `parbench audit-leak` checks it after the fact.
- S3 is not implemented.

## Minimal code to review (~250 lines total)

| Area | What to read |
|---|---|
| Token meter | `src/parbench/meter.py` `_handle`, `usage_from_body`, `start_for` |
| Token accounting | `agent_runner.py` the delta/subagent block (~l.170–185); `cli_agents.py` `AgyHarness.parse`, `_transcript_usage`, OpenCode `step_finish` branch |
| Model params and limits | `git diff b349dd2 -- configs/models.yaml`; `cli_agents.py` `_setup_v1`, `_limit()`; `scripts/serve/qwen38_27b.sh` l.5–13 |
| Account cycling | `src/parbench/agy_accounts.py` `pick`, `on_error`, `env_for`; the account-switch block in `agent_runner.py` |
| Gold hiding | `sandbox_policy.py` `hidden_paths`, `wrap_host`, `seatbelt_profile`; `landlock.py` `read_allow_list` |
| Service errors | `agent_runner.py` `_INFRA`, `_CONTEXT`, `service_error` |
| Merge fix and measurement changes | `merge.py` resolved check (~l.94–106); `strategies.py` `filter_test_files` line; `dataset.py` the two `rng =` lines |
