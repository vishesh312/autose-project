"""Combine per-agent patches into one tree: pairwise conflict probes + sequential merge per mode.

Modes (each yields its own final diff, graded separately):
  naive : `git merge`; a branch that conflicts is aborted and skipped (its task is then "lost in merge")
  union : same, with git's built-in union merge driver (keeps both sides of every conflicting hunk)
  llm   : `git merge`; on conflict, an agent (same harness + model) resolves the markers in place
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Callable

from .sandbox import Container

ResolverFn = Callable[[Container, list[str], list[int], Path], object]  # returns an AgentRecord


@dataclass
class MergeStep:
    branch: str
    feature_ids: list[int]
    conflicted: bool
    conflict_files: list[str] = field(default_factory=list)
    outcome: str = ""  # merged | skipped | resolved | resolve_failed | empty


@dataclass
class ModeResult:
    mode: str
    steps: list[MergeStep]
    final_patch: str
    lost_features: list[int]


def _branch_setup(c: Container, base_sha: str, patches: list[tuple[str, list[int], str]]) -> None:
    c.exec("git merge --abort 2>/dev/null; git reset -q --hard && git clean -fdq")
    for name, _, patch in patches:
        c.put_file(f"{c.work}/{name}.diff", patch)
        c.sh(f"git checkout -q -B {name} {base_sha}")
        if patch.strip():
            r = c.exec(f"git apply --index --binary {c.work}/{name}.diff || git apply --index --3way {c.work}/{name}.diff")
            if r.returncode != 0:
                raise RuntimeError(f"could not apply {name}'s own patch to base: {r.output[-800:]}")
        c.sh(f"git commit -q --allow-empty -m {name}")
    c.sh(f"git checkout -q --detach {base_sha}")


def _unmerged(c: Container) -> list[str]:
    return [f for f in c.exec("git diff --name-only --diff-filter=U").stdout.split() if f]


def pairwise_conflicts(c: Container, base_sha: str, names: list[str]) -> list[dict]:
    """Trial-merge every pair of agent branches; this is the conflict-rate metric."""
    out = []
    for a, b in combinations(names, 2):
        c.sh(f"git checkout -q -B _trial {a}")
        r = c.exec(f"git merge --no-commit --no-ff -q {b}")
        files = _unmerged(c) if r.returncode != 0 else []
        out.append({"a": a, "b": b, "conflict": r.returncode != 0, "files": files})
        c.exec("git merge --abort 2>/dev/null; git reset -q --hard")
    c.sh(f"git checkout -q --detach {base_sha}")
    return out


def merge_mode(
    c: Container,
    base_sha: str,
    patches: list[tuple[str, list[int], str]],
    mode: str,
    log_dir: Path,
    resolver: ResolverFn | None = None,
) -> tuple[ModeResult, list]:
    """Merge agent branches in the given (bundle) order. Returns (result, resolver agent records)."""
    attrs = f"{c.repo}/.git/info/attributes"
    c.exec(f"mkdir -p $(dirname {attrs}); " + (f"echo '* merge=union' > {attrs}" if mode == "union" else f"rm -f {attrs}"))
    steps, records, lost = [], [], []
    c.exec("git merge --abort 2>/dev/null; git reset -q --hard && git clean -fdq")
    c.sh(f"git checkout -q -B _merge_{mode} {base_sha}")
    for name, fids, patch in patches:
        if not patch.strip():
            steps.append(MergeStep(name, fids, False, outcome="empty"))
            continue
        r = c.exec(f"git merge --no-ff --no-edit -q {name}")
        if r.returncode == 0:
            steps.append(MergeStep(name, fids, False, outcome="merged"))
            continue
        files = _unmerged(c)
        step = MergeStep(name, fids, True, files)
        if mode == "llm" and resolver is not None and files:
            rec = resolver(c, files, fids, log_dir / f"resolver_{name}")
            records.append(rec)
            left = c.exec(
                "git diff --name-only --diff-filter=U; "
                + " ; ".join(f"grep -lE '^(<<<<<<<|>>>>>>>)( |$)' {shlex.quote(f)} 2>/dev/null" for f in files)
            ).stdout.split()
            if not left:
                c.sh("git add -A && { git commit -q --no-edit -m resolved || git commit -q -am resolved || git diff --cached --quiet; }")
                step.outcome = "resolved"
            else:
                c.exec("git merge --abort 2>/dev/null; git reset -q --hard")
                step.outcome = "resolve_failed"
                lost += fids
        else:
            c.exec("git merge --abort 2>/dev/null; git reset -q --hard")
            step.outcome = "skipped"
            lost += fids
        steps.append(step)
    c.exec(f"rm -f {attrs}")
    final = c.diff_against(base_sha)
    res = ModeResult(mode, steps, final, lost)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{mode}.diff").write_text(final)
    (log_dir / f"{mode}.json").write_text(
        json.dumps({"mode": mode, "lost": lost, "steps": [s.__dict__ for s in steps]}, indent=2)
    )
    return res, records


# ------------------------------------------------------------------ overlap metric
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def touched_base_lines(patch: str) -> set[tuple[str, int]]:
    """(file, base line) pairs a patch modifies. Pure insertions count the line they follow."""
    out: set[tuple[str, int]] = set()
    cur, line_no = None, 0
    for line in patch.splitlines():
        if line.startswith("diff --git"):
            m = re.match(r"diff --git a/(\S+) b/", line)
            cur = m.group(1) if m else None
        elif line.startswith("@@"):
            m = _HUNK.match(line)
            line_no = int(m.group(1)) if m else 0
        elif cur is None or line.startswith(("---", "+++")):
            continue
        elif line.startswith("-"):
            out.add((cur, line_no))
            line_no += 1
        elif line.startswith("+"):
            out.add((cur, max(line_no - 1, 0)))
        elif line.startswith(" "):
            line_no += 1
    return out


def overlap_lines(patches: list[str]) -> int:
    """Number of base lines touched by 2+ agents."""
    counts: dict[tuple[str, int], int] = {}
    for p in patches:
        for key in touched_base_lines(p):
            counts[key] = counts.get(key, 0) + 1
    return sum(1 for v in counts.values() if v >= 2)


def patch_files(patch: str) -> list[str]:
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", patch, re.M)))


def patch_line_count(patch: str) -> int:
    return sum(1 for l in patch.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
