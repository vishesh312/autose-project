#!/usr/bin/env bash
# Serve Qwen3.8-27B INT4 (RedHatAI, W4A16) on ONE GPU with a current vLLM. Check nvidia-smi first.
# Usage: GPU=0 scripts/serve/qwen38_27b.sh        (VENV / MODEL override the NVIDIA-box defaults)
# Must match configs/models.yaml `qwen3.8-27b-vllm`: SERVED_NAME = model, PORT in base_url, MAX_LEN = context.
# Model defaults throughout: sampling from generation_config.json (vllm.sh --generation-config auto), thinking on.
#   THINK=0  opt-out: thinking off for the whole server (not the model-card default; changes results).
#   MAX_LEN  default 262144 = native context. If the KV cache cannot hold one such sequence, vLLM refuses to start
#            and says how many tokens fit; then set MAX_LEN to that and the same `context` in models.yaml.
set -euo pipefail
source "${VENV:-/home/manasm/ase/.venv-vllm-new}/bin/activate"
export CUDA_VISIBLE_DEVICES="${GPU:?set GPU=<index of a free GPU>}"
MODEL="${MODEL:-/scratch/manas/Qwen3.8-27B-INT4}" SERVED_NAME=qwen3.8-27b-int4 PORT=8001 MAX_LEN="${MAX_LEN:-262144}" \
  MAX_SEQS="${MAX_SEQS:-4}" GPU_UTIL=0.92 KV_DTYPE=fp8 THINK="${THINK:-1}" TOOL_PARSER=qwen3_coder REASONING_PARSER=qwen3 \
  exec "$(dirname "$0")/vllm.sh"
