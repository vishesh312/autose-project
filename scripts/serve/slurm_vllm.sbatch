#!/bin/bash
# vLLM on a SLURM GPU node (written for IIIT Ada: 4x RTX 2080 Ti 11 GB, cc 7.5, no bf16).
#
# Submit from the repo root:
#   MODEL=<org>/Qwen3.6-27B-AWQ MAX_LEN=65536 MAX_SEQS=4 sbatch scripts/serve/slurm_vllm.sbatch
# Then read logs/vllm-<jobid>.out: it prints the node name and the ssh tunnel command.
# Everything in vllm.sh's env interface passes through (sbatch exports the submitting env by default).
# ASSUMPTIONS to check on Ada (not verified from here): account/partition names, whether compute
# nodes have internet (if not, pre-download weights on the login node into $HF_HOME), and
# that /scratch is node-local (copy weights there once per job for fast loading).
#SBATCH --job-name=vllm
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=16
#SBATCH --mem=60G
#SBATCH --time=12:00:00
#SBATCH --output=logs/vllm-%j.out
##SBATCH --account=<your_account>       # uncomment / set for Ada
##SBATCH --partition=<partition>
set -euo pipefail
: "${MODEL:?export MODEL=... before sbatch}"
export PORT="${PORT:-8000}" HOST=0.0.0.0
export TP="${TP:-$(nvidia-smi -L | wc -l)}"          # use all allocated GPUs
export DTYPE="${DTYPE:-half}"                        # 2080 Ti: fp16 only
export HF_HOME="${HF_HOME:-/scratch/$USER/hf}"       # keep weights off NFS home
mkdir -p "$HF_HOME" logs
# Activate the env that has vLLM (edit to taste):
[ -n "${VENV:-}" ] && source "$VENV/bin/activate"
# module load <cuda-module>   # Ada uses environment modules (`module avail cuda`); match your vLLM wheel

NODE=$(hostname)
cat <<MSG
=== vLLM job $SLURM_JOB_ID on $NODE, GPUs: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | paste -sd';')
Tunnel from your laptop (keep it open):
  ssh -N -L ${PORT}:${NODE}:${PORT} ${USER}@ada.iiit.ac.in
  # Linux laptop + Docker agents: bind the tunnel on all interfaces so host-gateway reaches it:
  ssh -N -L 0.0.0.0:${PORT}:${NODE}:${PORT} ${USER}@ada.iiit.ac.in
Then: python scripts/check_endpoint.py --base-url http://localhost:${PORT}/v1 --model <served-name> --parallel ${MAX_SEQS:-4}
Agents in Docker: http://host.docker.internal:${PORT}/v1
MSG

bash scripts/serve/vllm.sh "$@" &
VPID=$!
for _ in $(seq 180); do curl -sf -m 2 "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 10; done
SERVED="${SERVED_NAME:-$(basename "$MODEL" | tr '[:upper:]' '[:lower:]')}"
python3 scripts/check_endpoint.py --base-url "http://127.0.0.1:$PORT/v1" --model "$SERVED" \
  --anthropic --responses --parallel "${MAX_SEQS:-4}" --max-tokens 512 \
  --json-out "logs/vllm-$SLURM_JOB_ID-check.json" || echo "=== endpoint check FAILED (see above)"
wait $VPID
