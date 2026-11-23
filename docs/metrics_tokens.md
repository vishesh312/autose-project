# Token metrics: definitions and sources

Token counts are the main outcome of the study, so this page says what each number means, where it comes from,
and what is verified. Code: `config.Usage`, `meter.py`, the `parse` methods in `harnesses/cli_agents.py`,
`agent_runner.run_agent`, `runner.build_record`.

## Definitions (`Usage`, per model response, summed)

| Field | Meaning |
|---|---|
| `input` | all prompt tokens sent to the model, cached ones included (OpenAI `prompt_tokens`) |
| `cached_input` | the part of `input` served from the prompt cache (`prompt_tokens_details.cached_tokens`) |
| uncached input | `input - cached_input` (what list prices charge at the full input rate) |
| `cache_write` | prompt tokens written to a cache (Anthropic-style; 0 for OpenAI-compatible servers and agy) |
| `output` | all generated tokens, reasoning included (OpenAI `completion_tokens`) |
| `reasoning` | the part of `output` that was reasoning/thinking |
| `total` | `input + output` |
| `calls` | model responses counted |

Every model request counts: main session, subagent sessions, title generation, compaction, nudged and
retried attempts. Tokens of attempts that ended on a quota/capacity error or an account switch are included
and also shown separately (`usage_failed_attempts`).

## Sources, in order of preference

1. **Meter (`token_source: proxy`).** For `openai_compat` models parbench starts one reverse proxy per run on
   the host (`meter.py`, stdlib) and points the harness at `http://<host>:<port>/m/<agent>/v1`. It forwards
   requests and responses unchanged and reads the server's own `usage` (JSON body, or the last SSE chunk with
   `usage`). Per-request log: `agents/<id>/meter.jsonl`. Totals: `usage_proxy` per agent and per attempt,
   `cost.usage_proxy` per run. If any response of an agent had no usage (stream without
   `stream_options.include_usage`), that agent falls back to the harness numbers and `meter.requests_usage_missing`
   says how many; we never estimate. OpenCode 2.2.4 sends `include_usage: true` itself (seen in the meter
   log), so nothing is injected. On vLLM, start the server with `--enable-prompt-tokens-details` or
   `cached_tokens` is absent (counts as 0); `--enable-force-include-usage` covers clients that don't ask.
   Off with `PARBENCH_METER=0`.
2. **Harness-reported (`token_source: harness`).** Always recorded in `usage` per agent and `cost.usage_harness`
   per run, so the two can be compared. `cost.usage` (and `report`'s `tokens_*` columns) is the proxy number when
   every agent has a complete one, else the harness number (`token_source: mixed` if agents differ).

Networking: host mode and host pools (`PARBENCH_HOST_POOLS`) use `localhost:<port>`, the meter listens on
127.0.0.1. Docker mode uses `host.docker.internal:<port>` and the meter listens on 0.0.0.0 (Linux needs it for the
bridge; override `PARBENCH_METER_BIND`). The sandbox policy is computed from the metered URL, so seatbelt
(loopback only), Landlock (model port only) and docker-egress (socat to that port) all allow exactly the meter.
Docker mode is UNVERIFIED (Docker was down); host and host-pool mode are verified below.

## Harness mapping

| Harness | Field mapping | Per step or running total | Gaps |
|---|---|---|---|
| OpenCode 2.x | `step_finish.part.tokens`: `input` = non-cached input, `cache.read/write`, `output` = visible output only, `reasoning` separate (binary: `nonCachedInputTokens`, `visibleOutputTokens`). We set `input = input + cache.read + cache.write`, `output = output + reasoning`. | per step; a resumed session (`-s`) does not replay earlier steps | title generation (1 request per session) is not in the stream; **child (subagent) sessions are not in the stream** |
| OpenCode 1.x | same shape (vLLM runs) | per step | reasoning split UNVERIFIED (reasoning was 0) |
| agy | `step_update.usage` per model response: `input_tokens` excludes cache reads, `cache_read_tokens`, `output_tokens`, `thinking_tokens`. We set `input = input_tokens + cache_read_tokens`, `output = output_tokens + thinking_tokens` (thinking was 0 in every log; whether `output_tokens` already includes it is UNVERIFIED). | **`result.usage` is a running total for the whole conversation**; parbench sums the per-step usages of each attempt instead | subagents run in their own conversations, missing from both the stream and `result.usage`; parbench reads their `transcript.jsonl` (`subagent_info.log_uri`) and adds them (`usage_subagents`) |

## What was wrong before 2026-11-23, and its size

- **agy resumed attempts were double counted.** The parser took `result.usage` per attempt, but after
  `--conversation <id>` it includes every earlier attempt of that conversation (checked on all 223 attempts in
  `results/core_agy*`: `result_k - result_{k-1}` equals attempt k's step sum every time). Every nudge or
  infra retry (503 "No capacity") re-counted the conversation so far. `scripts/recheck_tokens.py` re-parses the
  logs: in `results/core_agy` GPT-OSS 120B was overcounted by +79% (S0), +97% (S1), +123% (S2), +9% (S4), up to
  +160% for one run; Gemini Flash +5% (S0, one run at +19%), S1/S2/S4 unaffected; all runs together +16%
  (344.2M recorded vs 296.2M). The error tracks the number of retries, not the strategy, so strategy
  comparisons on GPT-OSS were distorted. `results/` was not rewritten.
- **agy subagent tokens were missing** and `subagent_calls` was always 0 (subagent steps have
  `step_type: subagent` and no `tool_info`). No run in `results/core_agy*` used a subagent (no `subagent_info`
  in any log), so no existing number changes. In a one-prompt probe, two subagents added 30% on top of the
  main conversation.
- **OpenCode `output` excluded reasoning.** No effect so far (reasoning was 0 everywhere: thinking off).
- **OpenCode S4** omitted child sessions (known); the meter now counts them.
- Codex-style running totals did not reset when a new session started (e.g. infra retry without a session).

## Verification (2026-11-23, Mac, OpenCode 2.2.4 + Ollama `qwen3.5:9b`, toy pool in host-pool mode)

See the run numbers in `docs/findings.md`. agy: probe in a scratch directory with `parbench-clean-sub`
(`gemini-3.8-flash-low`): `result.usage` = sum of the main conversation's step usages = its transcript
(89,840 in / 643 out); the two subagent transcripts held another 39,157 in / 335 out, absent from `result.usage`.

## Not verifiable here

- What agy bills against quota (Google-side); we only see its reported usage. No proxy is possible for agy.
- Whether vLLM's `cached_tokens` matches its real prefix-cache hits (needs `--enable-prompt-tokens-details`).
- Docker-mode meter reachability (Linux bridge, Docker Desktop).
- Nested subagents (a subagent's own subagents) in agy: not seen; their transcripts would not be read.
