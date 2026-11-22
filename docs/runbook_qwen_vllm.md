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

The tool lists were read from the actual `/v1/chat/completions` requests (logging proxy in front of Ollama), not
from docs. Shell commands (`curl`, `pip download`, ...) are **not** blocked: only the web tools are removed.
Thinking off and temperature are sent per request (`reasoning_effort`, `temperature` from `configs/models.yaml`).

## 1. Serve

```bash
nvidia-smi                                    # pick a free GPU
GPU=0 scripts/serve/qwen38_27b.sh             # vLLM on :8001, served name qwen3.8-27b-int4, 64K ctx, thinking off
# VENV=/path/to/vllm-venv MODEL=/path/to/Qwen3.8-27B-INT4 GPU=0 scripts/serve/qwen38_27b.sh   # other paths
```

It must match `configs/models.yaml` `qwen3.8-27b-vllm`: `model` = `SERVED_NAME`, port in `base_url` = `PORT`,
`context` = `MAX_LEN` (65536). Tool parser `qwen3_coder`, reasoning parser `qwen3`, `enable_thinking: false`.

## 2. Check the endpoint (must exit 0)

```bash
python3 scripts/check_endpoint.py --base-url http://localhost:8001/v1 --model qwen3.8-27b-int4 \
    --parallel 4 --max-tokens 512 --json-out /tmp/qwen27b_endpoint.json
```

`tool_call` and `tool_roundtrip` must PASS (a wrong tool parser shows up as raw `<tool_call>` text in `content`).
Leave out `--no-think`: OpenCode does not send `chat_template_kwargs`, so this checks that the *server default* has
thinking off (`chat` should answer `'OK'` with `out_tok` of a few tokens in well under a second or two).
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

- A single turn can push the prompt over `65536 - max_output`; vLLM then returns a "maximum context length" error.
  OpenCode 1.19.5 recognises that message as a context overflow (pattern found in the binary), but whether it then
  compacts and continues was not observed.
- Tokens of OpenCode's title-generation call and of S4 child sessions are not in the JSON stream (docs/harnesses.md),
  so S4 token counts are a lower bound.
- `--default-chat-template-kwargs` (thinking off) needs a recent vLLM; check the vLLM log line printed by `vllm.sh`
  and that `check_endpoint.py` responses contain no `<think>` text.
