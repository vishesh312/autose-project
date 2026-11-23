# Runbook: OpenCode + Qwen3.8-27B on vLLM (NVIDIA box, no Docker)

For the teammate running the big OpenCode experiments. Box details: `docs/hardware_nvidia_box.md`. Background on
serving: `docs/serving_models.md`. Everything below runs from the repo root with the `parbench` venv active.

## What the harness does (checked 2026-11-23 on OpenCode 1.19.5 and 2.2.4)

OpenCode runs with its **default `build` agent, system prompt and tools**, with these exceptions, set in
`OpenCodeHarness` (`src/parbench/harnesses/cli_agents.py`):

| | 1.19.5 (this box) | 2.2.4 (Mac) |
|---|---|---|
| Tools the model sees, S0/S1/S2 | `bash edit glob grep read skill todowrite write` | `edit glob grep read shell skill write` + `opencode_*` (worktree/session/mcp helpers) |
| S4 adds | `task` | `subagent` |
| Removed | `webfetch`, `websearch`, `codesearch` (no internet), `question` (headless) | same, plus `execute` (Code Mode hides nested tool calls) |
| Approvals | `--auto` (anything not denied is approved); `external_directory` denied | `--auto` |
| System prompt vs. default config on a clean `HOME` | byte-identical (S0-S2 and S4) | identical except the Code Mode catalog (141 lines) that belongs to the denied `execute` tool |

The tool lists were read from the actual `/v1/chat/completions` requests (logging proxy in front of Ollama), not
from docs. Shell commands (`curl`, `pip download`, ...) are **not** blocked: only the web tools are removed.
### Model settings: model defaults, nothing set by us (decided 2026-11-23)

| Setting | What happens | Why |
|---|---|---|
| Sampling (temperature, top_p, top_k, ...) | **Nothing is sent.** vLLM applies the model's `generation_config.json` (`--generation-config auto`, vLLM's default in 0.8.5 and 0.33). OpenCode 1.19.5 adds sampling defaults only for Gemini, GLM, Kimi, MiniMax and DeepSeek ids (none for Qwen), and sends `temperature` only for models with `temperature: true`. 2.2.4 sent no sampling field (proxy) | User: use model-card defaults, no arbitrary constants |
| Thinking | **On** (Qwen3.8 model-card default). `THINK=0` in the serve script is an opt-out, off by default | Same. Thinking tokens count as output and fill the context faster |
| Output limit | `limit.output` = `limit.input` = `context`; 1.x gets `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=context` (its default cap is 32000). vLLM 0.33 lowers `max_tokens` to `max_model_len - prompt` itself (`get_max_tokens`), so the request never fails for that reason and output is limited only by the context. `input` = context keeps OpenCode's auto-compaction at `context - 20000` | User: as high as possible. Model card allows up to 131072 output (262144 with reasoning) |
| Context | `MAX_LEN` = 262144, the native length (was 65536) | More room for long sessions with thinking on. See the memory check below |

Qwen2.5-7B on vLLM 0.8.5 keeps `max_output: 8192` (its model-card generation limit): 0.8.5 rejects any request
with prompt + `max_tokens` > `max_model_len`, and OpenCode compacts at `context - max_output`.

## 1. Serve

```bash
nvidia-smi                                    # pick a free GPU
GPU=0 scripts/serve/qwen38_27b.sh             # vLLM on :8001, served name qwen3.8-27b-int4, 256K ctx, thinking on
# VENV=/path/to/vllm-venv MODEL=/path/to/Qwen3.8-27B-INT4 GPU=0 scripts/serve/qwen38_27b.sh   # other paths
```

It must match `configs/models.yaml` `qwen3.8-27b-vllm`: `model` = `SERVED_NAME`, port in `base_url` = `PORT`,
`context` = `MAX_LEN` (262144). Tool parser `qwen3_coder`, reasoning parser `qwen3`.

**Does 262144 fit in 32 GB?** Not checked. vLLM checks at startup: it refuses to start if one sequence of
`MAX_LEN` does not fit in the KV cache, and the error says how many tokens would fit. Read it from the log:

```bash
GPU=0 scripts/serve/qwen38_27b.sh 2>&1 | tee vllm27b.log
grep -E "GPU KV cache size|Maximum concurrency|max_model_len|larger than" vllm27b.log
```

If it does not fit, restart with `MAX_LEN=<value from the error, rounded down>` and put the same number in `context`
in `configs/models.yaml`. The tradeoff: a larger `MAX_LEN` means a longer session before compaction, but with
`MAX_SEQS=4` sequences sharing the KV cache, four long sessions at once can force vLLM to queue or preempt requests,
which shows up in the time metrics. The startup line `Maximum concurrency for N tokens per request` tells you how many full-length
sessions fit.

## 2. Check the endpoint (must exit 0)

```bash
python3 scripts/check_endpoint.py --base-url http://localhost:8001/v1 --model qwen3.8-27b-int4 \
    --parallel 4 --max-tokens 4096 --json-out /tmp/qwen27b_endpoint.json
```

`tool_call` and `tool_roundtrip` must PASS (a wrong tool parser shows up as raw `<tool_call>` text in `content`).
Leave out `--no-think`. With thinking on, `chat` spends tokens on reasoning first, hence `--max-tokens 4096`.
The reasoning should come back in `reasoning_content`, not as `<think>` text in `content` (reasoning parser).
`check_endpoint.py` sends its own `temperature 0` for these checks. That affects only the check, not the agents.
`parallel x4` should not say "looks SERIALISED". `--anthropic` / `--responses` are not needed for OpenCode.
(Same command shape verified on the Mac against Ollama, 2026-11-23: all checks PASS.)

## 3. Probe (one agent, one small prompt, no grading)

The toy pool needs Docker, so on the box probe a real pool with a tiny edit instead (`--toy` works on the Mac):

```bash
scripts/host_setup_pools.sh pallets_click_task/task2800          # once
PARBENCH_HOST_POOLS=<pools root> parbench probe --host --pool pallets_click_task/task2800 \
    --harness opencode --model qwen3.8-27b-vllm \
    --prompt "In src/click/__init__.py add the comment '# probe' as the last line. Do not change anything else."
```

Check in `results/_probes/opencode__qwen3.8-27b-vllm__*/`: the diff is that one line, `attempt0.stdout.jsonl`
has `step_finish` events with non-zero `tokens.input`, and there is no web tool:

```bash
grep -c '"tool":"web' results/_probes/opencode__qwen3.8-27b-vllm__*/attempt*.stdout.jsonl   # expect 0
```

## 4. One-bundle trial (click task2800, S1/S0/S2, ~1 h)

```bash
scripts/host_setup_pools.sh pallets_click_task/task2800          # once
PARBENCH_HOST_POOLS=<pools root> parbench run configs/experiments/qwen27b_click.yaml --dry-run
PARBENCH_HOST_POOLS=<pools root> parbench run configs/experiments/qwen27b_click.yaml
parbench report results/qwen27b_click
parbench audit-web results/qwen27b_click                         # expect no runs listed
```

Go on only if at least one task passes and there are no `error.txt` files from the pipeline (agent failures are fine).

## 5. Full run

`configs/experiments/qwen27b_core_DRAFT.yaml` is a draft with `TODO(decision)` for k, bundles per pool, repeats,
prompt extras and pool subset. After the decisions, rename it (drop `_DRAFT`), then:

```bash
scripts/host_setup_pools.sh <every pool in the config>          # once
PARBENCH_HOST_POOLS=<pools root> parbench run configs/experiments/qwen27b_core.yaml --dry-run   # count runs
nohup env PARBENCH_HOST_POOLS=<pools root> parbench run configs/experiments/qwen27b_core.yaml > qwen27b_core.log 2>&1 &
parbench report results/qwen27b_core && parbench audit-web results/qwen27b_core
```

Finished runs are skipped on relaunch. Keep `max_parallel_runs x k <= MAX_SEQS` (4) or the time metrics measure the
vLLM queue; raise `MAX_SEQS` in the serve script only if the KV cache fits (`vllm` logs the max concurrency at startup).

## Known limits (UNVERIFIED on the box)

- OpenCode compacts when the previous turn's total reaches `context - 20000`. A single turn that adds more than
  that (a huge tool output) makes the *prompt alone* exceed `MAX_LEN`, and vLLM rejects it. OpenCode 1.19.5 recognises
  that message as a context overflow (pattern found in the binary), but whether it then compacts and continues was
  not observed. A large `max_tokens` cannot cause this on vLLM 0.33 (it is lowered to fit; read in the v0.33.0rc3
  source, `vllm/entrypoints/serve/utils/api_utils.py:get_max_tokens`, not run).
- With thinking on, a turn can produce many thousand reasoning tokens. Expect more output tokens and longer turns
  than the thinking-off numbers in `docs/findings.md`.
- Tokens of OpenCode's title-generation call and of S4 child sessions are not in the JSON stream (docs/harnesses.md),
  so S4 token counts are a lower bound.
- Only if you opt out with `THINK=0`: `--default-chat-template-kwargs` needs a recent vLLM; check the vLLM log line
  printed by `vllm.sh` and that `check_endpoint.py` responses contain no `<think>` text.
