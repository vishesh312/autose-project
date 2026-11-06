#!/usr/bin/env bash
# Start (or reuse) an Ollama server configured for k parallel agents, pull the model, warm it, validate.
#
# Usage:  scripts/serve/ollama.sh [MODEL]
#   MODEL=qwen3.5:9b PARALLEL=4 CTX=65536 scripts/serve/ollama.sh
# Env (defaults):
#   MODEL=qwen3.5:9b   PORT=11434   BIND=0.0.0.0 (so Docker on Linux can reach it)
#   PARALLEL=4         -> OLLAMA_NUM_PARALLEL (Ollama default is 1 = requests are queued!)
#   CTX=65536          -> OLLAMA_CONTEXT_LENGTH, *per request slot* (Ollama default is 4096)
#   KV_TYPE=q8_0       -> OLLAMA_KV_CACHE_TYPE (f16|q8_0|q4_0; needs flash attention)
#   KEEP_ALIVE=-1      -> never unload between agent turns
#   VALIDATE=1         -> run scripts/check_endpoint.py afterwards (THINK=0 adds --no-think)
#   LOG=/tmp/ollama-$PORT.log
# KV memory ~= PARALLEL x CTX x (per-token KV bytes): check `ollama ps` after warm-up.
# Env vars only take effect when THIS script starts the server. If the macOS app is already
# serving on $PORT, quit it first (menu bar -> Quit Ollama) or pick another PORT; to configure
# the app itself use `launchctl setenv OLLAMA_NUM_PARALLEL 4` etc. and restart the app.
set -euo pipefail
MODEL="${1:-${MODEL:-qwen3.5:9b}}"
PORT="${PORT:-11434}"; BIND="${BIND:-0.0.0.0}"
PARALLEL="${PARALLEL:-4}"; CTX="${CTX:-65536}"; KV_TYPE="${KV_TYPE:-q8_0}"
KEEP_ALIVE="${KEEP_ALIVE:--1}"; VALIDATE="${VALIDATE:-1}"; THINK="${THINK:-1}"
LOG="${LOG:-/tmp/ollama-$PORT.log}"
OLLAMA="${OLLAMA:-$(command -v ollama)}"
URL="http://127.0.0.1:$PORT"
HERE="$(cd "$(dirname "$0")" && pwd)"

if curl -sf -m 3 "$URL/api/version" >/dev/null; then
  echo "[ollama.sh] server already running on :$PORT ($(curl -s "$URL/api/version"))."
  echo "[ollama.sh] WARNING: its PARALLEL/CTX/KV settings are whatever it was started with, not ours."
else
  echo "[ollama.sh] starting ollama serve on $BIND:$PORT (parallel=$PARALLEL ctx=$CTX kv=$KV_TYPE), log: $LOG"
  OLLAMA_HOST="$BIND:$PORT" OLLAMA_NUM_PARALLEL="$PARALLEL" OLLAMA_CONTEXT_LENGTH="$CTX" \
  OLLAMA_KV_CACHE_TYPE="$KV_TYPE" OLLAMA_FLASH_ATTENTION=1 OLLAMA_KEEP_ALIVE="$KEEP_ALIVE" \
  OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}" \
    nohup "$OLLAMA" serve >"$LOG" 2>&1 &
  echo $! > "/tmp/ollama-$PORT.pid"
  for _ in $(seq 60); do curl -sf -m 2 "$URL/api/version" >/dev/null && break; sleep 1; done
  curl -sf -m 2 "$URL/api/version" >/dev/null || { echo "server did not come up; see $LOG"; exit 1; }
fi

export OLLAMA_HOST="127.0.0.1:$PORT"   # for the CLI calls below
if ! "$OLLAMA" show "$MODEL" >/dev/null 2>&1; then
  echo "[ollama.sh] pulling $MODEL ..."; "$OLLAMA" pull "$MODEL"
fi

echo "[ollama.sh] warming $MODEL (num_ctx=$CTX, keep_alive=$KEEP_ALIVE)"
KA_JSON="$KEEP_ALIVE"; case "$KA_JSON" in -1|0|[0-9]*) ;; *) KA_JSON="\"$KA_JSON\"";; esac  # number or duration string
curl -sf -m 600 "$URL/api/generate" -d "{\"model\":\"$MODEL\",\"keep_alive\":$KA_JSON,\"options\":{\"num_ctx\":$CTX}}" >/dev/null
"$OLLAMA" ps
LOADED_CTX=$(curl -s "$URL/api/ps" | python3 -c "import json,sys;m=[x for x in json.load(sys.stdin)['models'] if x['name']=='$MODEL'];print(m[0].get('context_length','?') if m else '?')")
echo "[ollama.sh] loaded context_length=$LOADED_CTX (wanted $CTX)"
[ "$LOADED_CTX" = "$CTX" ] || echo "[ollama.sh] WARNING: context differs from CTX -- agents may be silently truncated."

if [ "$VALIDATE" = 1 ]; then
  ARGS=(--base-url "$URL/v1" --model "$MODEL" --anthropic --responses --parallel "$PARALLEL" --max-tokens "${MAX_TOKENS:-512}")
  [ "$THINK" = 0 ] && ARGS+=(--no-think)
  python3 "$HERE/../check_endpoint.py" "${ARGS[@]}" || true
fi
echo "[ollama.sh] containers: OPENAI base http://host.docker.internal:$PORT/v1 | ANTHROPIC_BASE_URL=http://host.docker.internal:$PORT"
