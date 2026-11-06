#!/bin/bash
# Toy grader with the CooperBench runner.sh contract.
set -e
TEST_PATCH="$1"
FEATURE_PATCH="$2"
cd /workspace/repo
git reset -q --hard HEAD
git clean -fdxq
if [[ -n "$FEATURE_PATCH" ]]; then
  git apply --ignore-whitespace "/patches/$FEATURE_PATCH" || git apply --3way "/patches/$FEATURE_PATCH"
fi
git apply --ignore-whitespace "/patches/$TEST_PATCH" || git apply --3way "/patches/$TEST_PATCH"
pip install -q --no-deps -e . >/dev/null 2>&1 || true
TEST_FILES=$(grep -oE '^\+\+\+ b/[^ ]+\.py' "/patches/$TEST_PATCH" | sed 's#^+++ b/##')
python -m pytest $TEST_FILES -v
