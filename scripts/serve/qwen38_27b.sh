#!/usr/bin/env bash
# Serve Qwen3.8-27B INT4 (RedHatAI, W4A16) on ONE GPU with a current vLLM, thinking off. Check nvidia-smi first.
# Usage: GPU=0 scripts/serve/qwen38_27b.sh
set -euo pipefail
source /home/manasm/ase/.venv-vllm-new/bin/activate
export CUDA_VISIBLE_DEVICES="${GPU:?set GPU=<index of a free GPU>}"
MODEL=/scratch/manas/Qwen3.8-27B-INT4 SERVED_NAME=qwen3.8-27b-int4 PORT=8001 MAX_LEN=65536 MAX_SEQS=4 \
  GPU_UTIL=0.92 KV_DTYPE=fp8 THINK=0 TOOL_PARSER=qwen3_coder REASONING_PARSER=qwen3 \
  exec "$(dirname "$0")/vllm.sh"
