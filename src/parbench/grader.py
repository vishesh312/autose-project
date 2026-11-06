"""Grade a final tree (as one diff vs base) against each feature's hidden tests, k >= 1.

Uses the pool image's own /usr/local/bin/runner.sh exactly like CooperBench's `_run_tests`;
`parse_results` and `filter_test_files` are ported from cooperbench/eval/sandbox.py (MIT).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from .dataset import Feature, Pool
from .sandbox import Container

TEST_TIMEOUT_S = 900


@dataclass
class TestResult:
    fid: int
    passed: bool
    exit_code: int
    tests_passed: int
    tests_failed: int
    duration_s: float
    log: str  # path to full log


def grade(pool: Pool, features: list[Feature], patch: str, log_dir: Path, label: str, parallel: int = 1,
          container_kw: dict | None = None) -> dict[int, TestResult]:
    """One container per worker; features are graded sequentially within a container (reset between)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    patch = filter_test_files(patch)
    (log_dir / f"{label}.graded.diff").write_text(patch)
    chunks = [features[i::parallel] for i in range(max(1, min(parallel, len(features))))]

    def work(chunk: list[Feature]) -> dict[int, TestResult]:
        out = {}
        with Container(pool.image, labels={"parbench.role": "grader"}, **(container_kw or {})) as c:
            base = c.base_sha()
            c.put_file("/patches/final.diff", patch)
            for f in chunk:
                c.put_path(f.tests_patch, f"/patches/tests{f.fid}.patch")
                feat_arg = "final.diff" if patch.strip() else ""
                r = c.exec(
                    "rm -f .git/index.lock; "
                    f"git checkout -q --force {base} && git reset -q --hard {base} && git clean -fdq; "
                    f"bash /usr/local/bin/runner.sh tests{f.fid}.patch {feat_arg}",
                    timeout=TEST_TIMEOUT_S,
                )
                parsed = parse_results(r.output)
                lp = log_dir / f"{label}.f{f.fid}.log"
                lp.write_text(r.output)
                out[f.fid] = TestResult(
                    f.fid, r.returncode == 0 and parsed["passed"] > 0, r.returncode,
                    parsed["passed"], parsed["failed"], r.ended - r.started, str(lp),
                )
        return out

    results: dict[int, TestResult] = {}
    with ThreadPoolExecutor(len(chunks)) as ex:
        for part in ex.map(work, chunks):
            results.update(part)
    (log_dir / f"{label}.json").write_text(json.dumps({k: asdict(v) for k, v in results.items()}, indent=2))
    return results


def parse_results(output: str) -> dict:
    """Pass/fail counts for pytest, go test, cargo test, jest/vitest."""
    m = re.search(r"Tests:\s*(?:(\d+)\s*failed,\s*)?(\d+)\s*passed", output)
    if m:
        return {"passed": int(m.group(2)), "failed": int(m.group(1) or 0)}
    passed = failed = 0
    if m := re.search(r"(\d+) passed", output):
        passed = int(m.group(1))
    if m := re.search(r"(\d+) failed", output):
        failed = int(m.group(1))
    if m := re.search(r"(\d+) error", output):
        failed += int(m.group(1))
    if passed or failed:
        return {"passed": passed, "failed": failed}
    go_pass, go_fail = len(re.findall(r"--- PASS:", output)), len(re.findall(r"--- FAIL:", output))
    if go_pass or go_fail:
        return {"passed": go_pass, "failed": go_fail}
    ok_pk = len(re.findall(r"^ok\s+\S+", output, re.M))
    fail_pk = len(re.findall(r"^FAIL\s+\S+", output, re.M))
    if ok_pk or fail_pk:
        return {"passed": ok_pk if fail_pk == 0 else 0, "failed": fail_pk}
    if m := re.search(r"test result:.*?(\d+) passed.*?(\d+) failed", output):
        return {"passed": int(m.group(1)), "failed": int(m.group(2))}
    return {"passed": 0, "failed": 0}


_TEST_DIR_RE = re.compile(r"/(tests?|__tests__|spec|testdata)/")
_TEST_FILE_RE = re.compile(
    r"(^|/)(test_[^/]+|[^/]+_test\.[A-Za-z0-9]+|[^/]+\.(test|spec)\.[A-Za-z0-9]+"
    r"|[^/]*Test[s]?\.(java|kt|cs|scala)|tests?\.py)$"
)


def _is_test_path(header: str) -> bool:
    paths = re.findall(r"[ab]/(\S+)", header)
    return any(_TEST_DIR_RE.search("/" + p) or _TEST_FILE_RE.search(p) for p in paths)


def filter_test_files(patch: str) -> str:
    """Drop agent-written test files: they collide with tests.patch and make `git apply` reject everything."""
    if not patch:
        return patch
    out, skip = [], False
    for line in patch.split("\n"):
        if line.startswith("diff --git"):
            skip = _is_test_path(line)
        if not skip:
            out.append(line)
    res = "\n".join(out)
    return res if res.endswith("\n") or not res else res + "\n"
