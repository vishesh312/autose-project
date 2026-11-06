#!/usr/bin/env python3
"""Proof of concept: build k-task bundles from real SWE-smith bugs with a controlled overlap ("conflict density")
and measure whether the tasks really conflict, using git only (no agents, no tests).

Plan steps covered (docs/swesmith_guide.md section 5.2): (1) take single-function bugs of one repository,
(2) index each bug's file, function and line range from its patch, (3) group k bugs by overlap level,
(4) apply all k bug patches to the clean commit and check that the bundle is valid.
Then, to measure conflicts the way parallel agents would produce them: each task's "fix" is the reverse of its bug
patch applied to the bundle snapshot; fixes are merged pairwise with `git merge`.

Usage: python3 scripts/swesmith_poc.py [--repo-query stanfordnlp__dspy] [--k 4] [--per-level 12]
Data: SWE-bench/SWE-smith (Hugging Face dataset server, queried with curl) and the repository mirror named in
each instance's `repo` field (github.com/swesmith/...). Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import collections
import itertools
import json
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "swesmith_poc"
SINGLE = ("func_pm_", "lm_modify", "lm_rewrite", "func_basic", "func_pm_class_rm", "func_pm_ctrl")


def curl_json(url: str) -> dict:
    r = subprocess.run(["curl", "-s", "-m", "120", url], capture_output=True, text=True)
    return json.loads(r.stdout)


def fetch_instances(query: str, pages: int) -> list[dict]:
    rows = []
    for p in range(pages):
        url = "https://datasets-server.huggingface.co/search?" + urllib.parse.urlencode(
            {"dataset": "SWE-bench/SWE-smith", "config": "default", "split": "train", "query": query,
             "offset": p * 100, "length": 100})
        got = []
        for attempt in range(5):  # the dataset server is flaky (auth timeouts), so retry
            try:
                d = curl_json(url)
            except Exception as e:  # noqa: BLE001
                d = {"error": str(e)}
            got = [r["row"] for r in d.get("rows", [])]
            if got or d.get("num_rows_total") == 0:
                break
            print(f"  page {p} attempt {attempt}: {str(d.get('error', 'empty'))[:90]}", flush=True)
            time.sleep(4)
        if not got:
            break
        rows += got
    return rows


def fetch_block(start: int, pages: int) -> list[dict]:
    """Read rows by offset (reliable endpoint). The dataset is grouped by repository, so one block = one repo."""
    rows = []
    first = None
    for p in range(pages):
        url = "https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode(
            {"dataset": "SWE-bench/SWE-smith", "config": "default", "split": "train", "offset": start + p * 100, "length": 100})
        got = []
        for attempt in range(4):
            try:
                got = [r["row"] for r in curl_json(url).get("rows", [])]
            except Exception:  # noqa: BLE001
                got = []
            if got:
                break
            time.sleep(3)
        if not got:
            break
        first = first or got[0]["repo"]
        keep = [r for r in got if r["repo"] == first]
        rows += keep
        if len(keep) < len(got):
            break
    return rows


def git(cwd: Path, *args: str, check=True, input=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=poc", "-c", "user.email=poc@local", "-c", "commit.gpgsign=false",
                           *args], cwd=cwd, capture_output=True, text=True, check=check, input=input)


def apply_bug(cwd: Path, patch: str) -> bool:
    """Apply one bug patch to the working tree. Strict `git apply` first; if the context was changed by an
    adjacent bug, fall back to `patch -F3` (fuzz), which is what lets bugs on nearby lines coexist."""
    if git(cwd, "apply", "-", input=patch, check=False).returncode == 0:
        return True
    r = subprocess.run(["patch", "-p1", "-F3", "--no-backup-if-mismatch", "-s", "-r", "-"], cwd=cwd, input=patch,
                       capture_output=True, text=True)
    return r.returncode == 0


def parse_patch(patch: str) -> dict[str, list[tuple[int, int]]]:
    """file -> list of (first, last) CHANGED line numbers on the OLD side (context lines are not counted).
    A pure insertion counts as the single old line it sits in front of."""
    out: dict[str, list[tuple[int, int]]] = collections.defaultdict(list)
    cur, old_no = None, 0
    for line in patch.splitlines():
        if line.startswith("diff --git"):
            m = re.match(r"diff --git a/(\S+) b/", line)
            cur = m.group(1) if m else None
        elif line.startswith("@@") and cur:
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+", line)
            old_no = int(m.group(1))
        elif cur and not line.startswith(("+++", "---")):
            if line.startswith("-"):
                out[cur].append((old_no, old_no))
                old_no += 1
            elif line.startswith("+"):
                out[cur].append((old_no, old_no))
            elif line.startswith(" "):
                old_no += 1
    merged: dict[str, list[tuple[int, int]]] = {}
    for f, rs in out.items():
        rs.sort()
        cur_rs = [rs[0]]
        for x, y in rs[1:]:
            if x <= cur_rs[-1][1] + 1:
                cur_rs[-1] = (cur_rs[-1][0], max(cur_rs[-1][1], y))
            else:
                cur_rs.append((x, y))
        merged[f] = cur_rs
    return merged


def function_at(base: Path, file: str, lines: list[tuple[int, int]], cache: dict) -> set[str]:
    """Innermost enclosing function (or <module>) for each changed range, via ast on the clean file."""
    if file not in cache:
        try:
            cache[file] = ast.parse((base / file).read_text())
        except Exception:
            cache[file] = None
    tree = cache[file]
    names = set()
    for a, b in lines:
        best = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= a and b <= (node.end_lineno or node.lineno):
                    if best is None or node.lineno >= best.lineno:
                        best = node
        names.add(f"{file}::{best.name}@{best.lineno}" if best else f"{file}::<module>")
    return names


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-query", default="stanfordnlp__dspy")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--start", type=int, default=None, help="row offset of a repository block (uses the reliable rows endpoint)")
    ap.add_argument("--per-level", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    rows = fetch_block(args.start, args.pages) if args.start is not None else fetch_instances(args.repo_query, args.pages)
    if not rows:
        sys.exit("no instances fetched from the dataset server")
    repos = collections.Counter(r["repo"] for r in rows)
    repo = repos.most_common(1)[0][0]
    rows = [r for r in rows if r["repo"] == repo and any(s in r["instance_id"] for s in SINGLE)
            and "combine_" not in r["instance_id"] and "pr_" not in r["instance_id"]]
    print(f"repo {repo}: {len(rows)} single-entity instances fetched", flush=True)

    work = Path(tempfile.mkdtemp(prefix="swesmith-poc-"))
    base = work / "base"
    r = subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{repo}.git", str(base)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"clone failed: {r.stderr[:300]}")
    base_sha = git(base, "rev-parse", "HEAD").stdout.strip()

    # ---- step 2: index bugs (file, function, line ranges); keep those that apply cleanly to the clean commit
    cache: dict = {}
    bugs = []
    for row in rows:
        patch = row["patch"]
        if not patch.endswith("\n"):
            patch += "\n"
        if git(base, "apply", "--check", "-", input=patch, check=False).returncode != 0:
            continue
        # Positions come from git's own minimal diff of the bug, not from the patch text: SWE-smith patches often
        # rewrite a whole function body while changing only a few lines, which would hugely overstate the overlap.
        git(base, "apply", "-", input=patch)
        spans = parse_patch(git(base, "diff", "-U0").stdout)
        git(base, "reset", "-q", "--hard")
        git(base, "clean", "-fdq")
        funcs = set()
        for f, lines in spans.items():
            funcs |= function_at(base, f, lines, cache)
        bugs.append(dict(id=row["instance_id"], patch=patch, files=sorted(spans), spans=spans, funcs=sorted(funcs),
                         f2p=len(row["FAIL_TO_PASS"]) if isinstance(row["FAIL_TO_PASS"], list) else None))
    single = [b for b in bugs if len(b["files"]) == 1 and len(b["funcs"]) == 1]
    print(f"{len(bugs)} apply cleanly; {len(single)} touch exactly one file and one function", flush=True)

    def lines_overlap(a, b, margin=3):
        f = a["files"][0]
        if f != b["files"][0]:
            return False
        return any(x1 - margin <= y2 and y1 - margin <= x2 for x1, x2 in a["spans"][f] for y1, y2 in b["spans"][f])

    by_file = collections.defaultdict(list)
    by_func = collections.defaultdict(list)
    for b in single:
        by_file[b["files"][0]].append(b)
        by_func[b["funcs"][0]].append(b)

    # ---- step 3: bundles by overlap level (k bugs each)
    k = args.k
    levels: dict[str, list[list[dict]]] = {"L0 different files": [], "L1 same file, different functions": [],
                                           "L2a two bugs in one function": [], "L2b all k bugs in one function": [],
                                           "L3 two bugs on adjacent lines": []}
    files = [f for f, v in by_file.items() if v]
    for _ in range(400):
        if len(levels["L0 different files"]) >= args.per_level:
            break
        fs = rng.sample(files, k) if len(files) >= k else []
        if fs:
            levels["L0 different files"].append([rng.choice(by_file[f]) for f in fs])
    for f, v in by_file.items():
        funcs = collections.defaultdict(list)
        for b in v:
            funcs[b["funcs"][0]].append(b)
        if len(funcs) >= k:
            for _ in range(20):
                if len(levels["L1 same file, different functions"]) >= args.per_level:
                    break
                fn = rng.sample(list(funcs), k)
                levels["L1 same file, different functions"].append([rng.choice(funcs[x]) for x in fn])
    for fn, v in by_func.items():
        if len(v) >= 2:
            ok = [b for b in v]
            for _ in range(10):
                if len(levels["L2a two bugs in one function"]) >= args.per_level:
                    break
                two = rng.sample(ok, 2)
                others = [rng.choice(by_file[f]) for f in rng.sample([x for x in files if x != two[0]["files"][0]], k - 2)]
                levels["L2a two bugs in one function"].append(two + others)
        if len(v) >= k:
            for _ in range(10):
                if len(levels["L2b all k bugs in one function"]) >= args.per_level:
                    break
                levels["L2b all k bugs in one function"].append(rng.sample(v, k))
    def intersects(a, b):
        f = a["files"][0]
        return f == b["files"][0] and any(x1 <= y2 and y1 <= x2 for x1, x2 in a["spans"][f] for y1, y2 in b["spans"][f])

    def gap(a, b):
        """Unchanged lines between the closest hunks of two bugs in one file (negative = overlapping)."""
        f = a["files"][0]
        return min(max(x1, y1) - min(x2, y2) - 1 for x1, x2 in a["spans"][f] for y1, y2 in b["spans"][f])

    adj = []
    for fn, v in by_func.items():
        adj += [(gap(a, b), a, b) for a, b in itertools.combinations(v, 2) if not intersects(a, b) and gap(a, b) <= 0]
    rng.shuffle(adj)
    for g, a, b in adj:
        if len(levels["L3 two bugs on adjacent lines"]) >= args.per_level:
            break
        others = [rng.choice(by_file[f]) for f in rng.sample([x for x in files if x != a["files"][0]], k - 2)]
        levels["L3 two bugs on adjacent lines"].append([a, b] + others)
    print(f"  adjacent-line pairs available (gap<=0, i.e. touching changed lines): {len(adj)}", flush=True)
    for lv, bl in levels.items():
        print(f"  {lv}: {len(bl)} candidate bundles", flush=True)

    # ---- step 4 + conflict measurement
    results = {}
    for lv, bundles in levels.items():
        rec = []
        for bundle in bundles:
            ids = [b["id"] for b in bundle]
            if len(set(ids)) < k:
                continue
            def build(branch, subset):
                git(base, "reset", "-q", "--hard")
                git(base, "clean", "-fdq")
                git(base, "checkout", "-q", "-B", branch, base_sha)
                if not all(apply_bug(base, bug["patch"]) for bug in subset):
                    return None
                git(base, "add", "-A")
                git(base, "commit", "-q", "--allow-empty", "-m", branch)
                return git(base, "rev-parse", "HEAD").stdout.strip()

            snap = build("snap", bundle)
            if snap is None:
                rec.append(dict(valid=False, reason="bug patches do not apply together"))
                continue
            fixes = []
            for i in range(k):
                t = build(f"t{i}", [bug for j, bug in enumerate(bundle) if j != i])
                ok = t is not None
                if ok:
                    git(base, "reset", "-q", "--hard")
                    git(base, "checkout", "-q", "-B", f"fix{i}", snap)
                    git(base, "checkout", f"t{i}", "--", ".")
                    git(base, "add", "-A")
                    git(base, "commit", "-q", "--allow-empty", "-m", f"fix {i}")
                fixes.append(ok)
            pairs = []
            detail = []
            for i, j in itertools.combinations(range(k), 2):
                if not (fixes[i] and fixes[j]):
                    continue
                git(base, "reset", "-q", "--hard")
                git(base, "checkout", "-q", "-B", "m", f"fix{i}")
                m = git(base, "merge", "--no-edit", "-q", f"fix{j}", check=False)
                pairs.append(m.returncode != 0)
                detail.append(dict(a=bundle[i]["id"][-12:], b=bundle[j]["id"][-12:], same_file=bundle[i]["files"][0] == bundle[j]["files"][0],
                                   gap=(gap(bundle[i], bundle[j]) if bundle[i]["files"][0] == bundle[j]["files"][0] else None),
                                   spans_a=bundle[i]["spans"][bundle[i]["files"][0]][:3], spans_b=bundle[j]["spans"][bundle[j]["files"][0]][:3],
                                   conflict=m.returncode != 0, merge_err=(m.stdout + m.stderr)[:120]))
                git(base, "merge", "--abort", check=False)
                git(base, "reset", "-q", "--hard")
            git(base, "checkout", "-q", "-B", "all", snap)
            merged = 0
            for i in range(k):
                if fixes[i] and git(base, "merge", "--no-edit", "-q", f"fix{i}", check=False).returncode == 0:
                    merged += 1
                else:
                    git(base, "merge", "--abort", check=False)
            restored = git(base, "diff", "--quiet", base_sha, check=False).returncode == 0
            same_file_pairs = sum(1 for a, b in itertools.combinations(bundle, 2) if a["files"][0] == b["files"][0])
            same_func_pairs = sum(1 for a, b in itertools.combinations(bundle, 2) if a["funcs"][0] == b["funcs"][0])
            near_pairs = sum(1 for a, b in itertools.combinations(bundle, 2) if lines_overlap(a, b))
            npairs = k * (k - 1) // 2
            rec.append(dict(valid=True, ids=ids, same_file_frac=same_file_pairs / npairs, same_func_frac=same_func_pairs / npairs,
                            near_frac=near_pairs / npairs, reversible=all(fixes), conflict_rate=(sum(pairs) / len(pairs)) if pairs else None,
                            fixes_merged=merged, fully_restored=restored, pair_detail=detail))
        results[lv] = rec

    # ---- summary
    summary = []
    for lv, rec in results.items():
        v = [r for r in rec if r.get("valid")]
        cr = [r["conflict_rate"] for r in v if r["conflict_rate"] is not None]
        summary.append(dict(level=lv, bundles=len(rec), valid=len(v),
                            same_file=statistics.mean(r["same_file_frac"] for r in v) if v else None,
                            same_func=statistics.mean(r["same_func_frac"] for r in v) if v else None,
                            near=statistics.mean(r["near_frac"] for r in v) if v else None,
                            conflict=statistics.mean(cr) if cr else None,
                            restored=statistics.mean(1.0 if r["fully_restored"] else 0.0 for r in v) if v else None))
    (OUT / "summary.json").write_text(json.dumps(dict(repo=repo, base_sha=base_sha, k=k, seed=args.seed, summary=summary,
                                                     bundles=results, n_indexed=len(bugs), n_single=len(single)), indent=1))
    print(json.dumps(summary, indent=1))
    # LaTeX table
    def f(x):
        return "--" if x is None else f"{x:.2f}"
    lines = [r"\begin{tabular}{@{}lrcccc@{}}", r"\toprule",
             r"Overlap level & Bundles & Same fn & Near & Conflict & Restored \\", r"\midrule"]
    for s in summary:
        lines.append(f"{s['level']} & {s['valid']} & {f(s['same_func'])} & {f(s['near'])} & {f(s['conflict'])} & {f(s['restored'])} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (ROOT / "report" / "tables_swesmith.tex").write_text("\n".join(lines) + "\n")
    print("done")


if __name__ == "__main__":
    main()
