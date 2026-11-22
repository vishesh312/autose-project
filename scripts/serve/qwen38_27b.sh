#!/usr/bin/env bash
# Serve Qwen3.8-27B INT4 (RedHatAI, W4A16) on ONE GPU with a current vLLM, thinking off. Check nvidia-smi first.
# Usage: GPU=0 scripts/serve/qwen38_27b.sh        (VENV / MODEL override the NVIDIA-box defaults)
# Must match configs/models.yaml `qwen3.8-27b-vllm`: SERVED_NAME = model, PORT in base_url, MAX_LEN = context.
set -euo pipefail
source "${VENV:-/home/manasm/ase/.venv-vllm-new}/bin/activate"
export CUDA_VISIBLE_DEVICES="${GPU:?set GPU=<index of a free GPU>}"
MODEL="${MODEL:-/scratch/manas/Qwen3.8-27B-INT4}" SERVED_NAME=qwen3.8-27b-int4 PORT=8001 MAX_LEN=65536 \
  MAX_SEQS="${MAX_SEQS:-4}" GPU_UTIL=0.92 KV_DTYPE=fp8 THINK=0 TOOL_PARSER=qwen3_coder REASONING_PARSER=qwen3 \
  exec "$(dirname "$0")/vllm.sh"
