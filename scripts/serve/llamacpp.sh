#!/usr/bin/env bash
# Start llama.cpp's llama-server (GGUF) for k parallel agents. Works on Mac (Metal), CUDA (any cc,
# incl. 1080 Ti / 2080 Ti), and CPU. Exposes /v1/chat/completions, /v1/responses, /v1/messages.
#
# Usage:  scripts/serve/llamacpp.sh [extra llama-server args...]
#   HF=unsloth/Qwen3.6-35B-A3B-GGUF:Q4_K_M NP=4 CTX_PER_SLOT=65536 scripts/serve/llamacpp.sh
#   GGUF=/models/devstral-small-2-Q4_K_M.gguf scripts/serve/llamacpp.sh -ts 1,1   # split over 2 GPUs
# Env (defaults):
#   HF=<repo>[:quant] (downloaded via -hf)  or  GGUF=<local file>      ALIAS=model name in the API
#   PORT=8080  HOST=0.0.0.0   NP=4 (parallel slots = k agents)   CTX_PER_SLOT=65536
#   KV_TYPE=q8_0 (cache-type-k/v; quantised V needs flash attention, which we force on)
#   NGL=all (layers on GPU)   THINK=1 (THINK=0 -> chat template enable_thinking=false)
# Total KV = NP x CTX_PER_SLOT: we pass -c $((NP*CTX_PER_SLOT)) with a non-unified KV cache, so each
# slot gets exactly CTX_PER_SLOT tokens. Verify with: curl localhost:$PORT/slots | grep n_ctx
set -euo pipefail
PORT="${PORT:-8080}"; HOST="${HOST:-0.0.0.0}"; NP="${NP:-4}"; CTX_PER_SLOT="${CTX_PER_SLOT:-65536}"
KV_TYPE="${KV_TYPE:-q8_0}"; NGL="${NGL:-all}"; THINK="${THINK:-1}"
if   [ -n "${GGUF:-}" ]; then SRC=(-m "$GGUF"); ALIAS="${ALIAS:-$(basename "$GGUF" .gguf)}"
elif [ -n "${HF:-}" ];   then SRC=(-hf "$HF");  ALIAS="${ALIAS:-$(basename "${HF%%:*}" | tr '[:upper:]' '[:lower:]')}"
else echo "set GGUF=<file.gguf> or HF=<repo>[:quant]"; exit 1; fi

ARGS=("${SRC[@]}" --alias "$ALIAS" --host "$HOST" --port "$PORT" --jinja
      -np "$NP" -c $((NP * CTX_PER_SLOT)) --no-kv-unified
      -ngl "$NGL" -fa on -ctk "$KV_TYPE" -ctv "$KV_TYPE" --metrics)
[ "$THINK" = 0 ] && ARGS+=(--chat-template-kwargs '{"enable_thinking": false}')

echo "[llamacpp.sh] $(llama-server --version 2>&1 | grep -m1 -i version || echo 'version ?')"
echo "[llamacpp.sh] llama-server ${ARGS[*]} $*"
echo "[llamacpp.sh] when ready: python scripts/check_endpoint.py --base-url http://localhost:$PORT/v1 --model $ALIAS --anthropic --responses --parallel $NP"
exec llama-server "${ARGS[@]}" "$@"
