#!/usr/bin/env bash
# No-Docker pool setup: for each CooperBench pool, clone the repo at the base commit and build one shared venv.
# parbench (PARBENCH_HOST_POOLS=<root>) copies <root>/<repo>/task<id>/repo per workspace and runs with that venv's
# PATH, with PYTHONPATH pointing at the workspace copy (so the editable install in the template is shadowed).
# Usage: scripts/host_setup_pools.sh pallets_jinja_task/task1559 ...   (Python pools only; see docs)
set -uo pipefail
ROOT="${PARBENCH_HOST_POOLS:-/scratch/manas/parbench/pools}"
DS="$(cd "$(dirname "$0")/.." && pwd)/external/CooperBench/dataset"
export PATH="$HOME/.cargo/bin:$PATH"
mkdir -p "$ROOT"

setup_one() {
  local pool="$1" d="$DS/$1" out="$ROOT/$1"
  local url commit pyver=3.11
  url=$(grep -oE "git clone [^ ]+" "$d/Dockerfile" | head -1 | awk '{print $3}')
  commit=$(grep -oE "checkout [0-9a-f]{7,40}" "$d/Dockerfile" | head -1 | awk '{print $2}')
  grep -q "python:3.10" "$d/Dockerfile" && pyver=3.10
  echo "[$pool] $url @ $commit (python $pyver)"
  mkdir -p "$out"
  [ -d "$out/repo/.git" ] || git clone -q "$url" "$out/repo" || return 1
  git -C "$out/repo" checkout -q --force "$commit" || return 1
  [ -d "$out/venv" ] || uv venv -q --python "$pyver" "$out/venv" || return 1
  local py="$out/venv/bin/python"
  cd "$out/repo"
  case "$pool" in
    dspy_task/*)        uv pip install -q --python "$py" -e ".[dev]" "litellm==1.77.1" ;;
    llama_index_task/*) uv pip install -q --python "$py" -r pyproject.toml || uv pip install -q --python "$py" -e . ;;
    *)                  uv pip install -q --python "$py" -e ".[test]" || uv pip install -q --python "$py" -e . ;;
  esac
  uv pip install -q --python "$py" pytest pytest-xdist pytest_mock regex hypothesis openai
  printf '*.egg-info/\nbuild/\n*.so\n__pycache__/\n.pytest_cache/\n.hypothesis/\ntarget/\n' >> "$out/repo/.git/info/exclude"  # editable-install artifacts must not enter agent diffs
  echo "[$pool] done" | tee "$out/READY"
}

for p in "$@"; do setup_one "$p" > "$ROOT/$(echo "$p" | tr / _).setup.log" 2>&1 && echo "OK $p" || echo "FAIL $p (see $ROOT/*.setup.log)" & done
wait
