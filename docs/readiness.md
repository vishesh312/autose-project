# Readiness for big runs (2026-11-23)

Four independent agents each checked one area: Antigravity, OpenCode with vLLM, sandboxing, and the orchestration audit. All four branches are merged into `main`; compile, `pytest tests/` (7 tests) and dry runs of `toy_agy`, `toy_smoke`, `qwen27b_core_DRAFT` and `core_agy_click` pass.

## Verdict

| Path | Ready? | Blocking items |
|---|---|---|
| `agy` (Gemini, GPT-OSS) on the Mac | **Yes, after the to-dos** | Log in accounts 2 and 3. Docker must be up (host clones are made from the pool images). Run one toy probe on the merged code. |
| OpenCode + Qwen3.8-27B on vLLM (GPU box) | **Ready for the one-bundle trial**, not yet the big run | Follow `docs/runbook_qwen_vllm.md`. The 27B model has not been run; the tool parser and whether `MAX_LEN` 262144 fits can only be checked on the box. |
| Sandbox | **Built, opt-in (`sandbox: off` by default)** | No real agent has run inside it yet (Docker went down mid-test). Linux box: run `scripts/sandbox_selftest.sh` first. |
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
| Bundles are seeded per pool | Before, a pool's task order depended on which other pools a config listed, so harnesses ran different bundles. |

## Bugs fixed that affect earlier numbers

1. **S2 LLM merge:** a resolver that removed conflict markers without `git add` was counted as failed and its work thrown away (seen in the go_chi 27 S2 run). Earlier S2 `llm` numbers with conflicts are suspect.
2. **Prompts:** the nudge, resolver and S4-worktree prompts sent a literal `${repo}`.

The other fixes are robustness fixes: Ctrl-C handling, container cleanup on setup failure, atomic `run.json`, stale-log handling, all `+extra` snippets applied, the resolver's harness files kept out of the diff, and graded-once caching.

## To-dos for the user

1. Restart Docker Desktop. It returns HTTP 500 at the moment.
2. Run `scripts/agy_login_account.sh 2` and then `3`, signing in with the second and third Google accounts.
3. Done: the 5 default `agy` system-prompt sections are now in the custom agents. Remove the probe agents `parbench-probe-*.md` from `~/.gemini/config/agents/`, otherwise S4 lists them as subagents. Old note: `--agent` drops them, including "work efficiently"; with them restored, `agy` behaves as by default minus web.
4. Teammate on the GPU box: follow the runbook, run `scripts/sandbox_selftest.sh http://localhost:8000/v1/models`, then the `qwen27b_click` trial.
5. Fill the `TODO(decision)` lines in `configs/experiments/qwen27b_core_DRAFT.yaml`: k, bundles per pool, repeats and prompt extras (temperature is no longer set: model defaults).

## Known gaps (not fixed)

- Host-mode agents can read the dataset's gold patches on the host filesystem; nothing hides them yet.
- Runs that fail on quota or capacity are left out of reports but never retried automatically.
- Wall-clock time is measured slightly differently per strategy (S0 includes container setup; S2 includes merging).
- S4 token counts for OpenCode are a lower bound, because child sessions are not in the JSON output.
- `agy` copies its agent files into the profiles without a lock (possible race, unverified).
- 50 stale `parbench-host-*` directories sit in `$TMPDIR`; safe to delete when nothing is running.
- S3 is not implemented.

## Minimal code to review (~200 lines total)

| Area | What to read |
|---|---|
| Account cycling | `src/parbench/agy_accounts.py` `pick`, `on_error`, `env_for`; the account-switch block in `agent_runner.py` (before the infra-wait block) |
| OpenCode tools | `git show c6516a6 -- src/parbench/harnesses/cli_agents.py` (~30 lines) |
| Merge fix | `src/parbench/merge.py` resolved check (~l.94–106) |
| Measurement changes | `strategies.py` `patches = [... filter_test_files ...]`; `dataset.py` the two `rng =` lines |
| Sandbox | `sandbox_policy.py` `describe()` and the `require` check; `landlock.py` `restrict()` |
