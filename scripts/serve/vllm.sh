#!/usr/bin/env bash
# Start vLLM's OpenAI/Anthropic/Responses-compatible server with the right tool + reasoning parsers.
#
# Usage:  scripts/serve/vllm.sh [extra vllm serve args...]
#   MODEL=Qwen/Qwen3.6-35B-A3B-FP8 MAX_LEN=131072 MAX_SEQS=4 scripts/serve/vllm.sh
#   MODEL=<some-org>/Devstral-Small-2-24B-AWQ TP=4 scripts/serve/vllm.sh   # 4x2080 Ti (pick a real AWQ repo)
# Env (defaults):
#   MODEL (required)  SERVED_NAME=basename of MODEL, lower-cased, no "/" (Claude Code needs that)
#   PORT=8000  HOST=0.0.0.0   MAX_LEN=65536 (per-request context)   MAX_SEQS=4 (= k agents)
#   GPU_UTIL=0.90   TP=1 (tensor parallel = #GPUs)   DTYPE=auto (auto-forced to half on cc<8.0)
#   QUANT=   (empty = read from checkpoint; e.g. awq_marlin, gptq_marlin, fp8)
#   KV_DTYPE=auto  (fp8 halves KV memory; on Turing it is a storage-only format - test it)
#   TOOL_PARSER / REASONING_PARSER: auto-picked from MODEL name below; set to override,
#                                   REASONING_PARSER=none to disable.
#   THINK=1  (THINK=0 -> --default-chat-template-kwargs '{"enable_thinking": false}')
# Prints the exact command it runs; keep that line in the run log.
set -euo pipefail
: "${MODEL:?set MODEL=<hf repo or local path>}"
PORT="${PORT:-8000}"; HOST="${HOST:-0.0.0.0}"
MAX_LEN="${MAX_LEN:-65536}"; MAX_SEQS="${MAX_SEQS:-4}"; GPU_UTIL="${GPU_UTIL:-0.90}"
TP="${TP:-1}"; DTYPE="${DTYPE:-auto}"; KV_DTYPE="${KV_DTYPE:-auto}"; THINK="${THINK:-1}"
SERVED_NAME="${SERVED_NAME:-$(basename "$MODEL" | tr '[:upper:]' '[:lower:]')}"

m="$(echo "$MODEL" | tr '[:upper:]' '[:lower:]')"
case "$m" in   # parser names checked against docs.vllm.ai tool_calling / reasoning_outputs (Nov 2026)
  *qwen3-coder*)                     tp=qwen3_coder;  rp=none   ;;  # Coder models don't think
  *ornith*)                          tp=qwen3_xml;    rp=qwen3  ;;  # per Ornith model card
  *qwen3.5*|*qwen3.6*|*qwen3.8*)     tp=qwen3_coder;  rp=qwen3  ;;  # per Qwen3.6 card / vLLM recipe
  *devstral*|*mistral*|*ministral*)  tp=mistral;      rp=none   ;;
  *gpt-oss*)                         tp=openai;       rp=none   ;;  # harmony format handled natively
  *glm-4.7*)                         tp=glm47;        rp=glm45  ;;
  *glm-4.5*|*glm-4.6*)               tp=glm45;        rp=glm45  ;;
  *)                                 tp=hermes;       rp=none   ;;  # generic guess - verify!
esac
TOOL_PARSER="${TOOL_PARSER:-$tp}"; REASONING_PARSER="${REASONING_PARSER:-$rp}"

if [ "$DTYPE" = auto ] && command -v nvidia-smi >/dev/null; then
  cc=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d ' ')
  case "$cc" in 6.*|7.*) DTYPE=half; echo "[vllm.sh] compute capability $cc: no bf16 -> --dtype half";; esac
fi

ARGS=(serve "$MODEL" --served-model-name "$SERVED_NAME" --host "$HOST" --port "$PORT"
      --max-model-len "$MAX_LEN" --max-num-seqs "$MAX_SEQS" --gpu-memory-utilization "$GPU_UTIL"
      --tensor-parallel-size "$TP" --dtype "$DTYPE" --kv-cache-dtype "$KV_DTYPE"
      --enable-prefix-caching --enable-auto-tool-choice --tool-call-parser "$TOOL_PARSER"
      --generation-config auto)
[ "$REASONING_PARSER" != none ] && ARGS+=(--reasoning-parser "$REASONING_PARSER")
[ -n "${QUANT:-}" ] && ARGS+=(--quantization "$QUANT")
[ "$THINK" = 0 ] && ARGS+=(--default-chat-template-kwargs '{"enable_thinking": false}')
case "$m" in *ornith*) ARGS+=(--trust-remote-code);; esac

echo "[vllm.sh] vllm $(vllm --version 2>/dev/null || echo '?') | $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | sort | uniq -c | tr '\n' ' ')"
echo "[vllm.sh] vllm ${ARGS[*]} $*"
echo "[vllm.sh] when ready: python scripts/check_endpoint.py --base-url http://localhost:$PORT/v1 --model $SERVED_NAME --anthropic --responses --parallel $MAX_SEQS"
exec vllm "${ARGS[@]}" "$@"
