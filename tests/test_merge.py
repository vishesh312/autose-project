"""Merge modes on a local git repo (no Docker): HostWorkspace pointed at a repo we build ourselves."""

import subprocess
from pathlib import Path

from parbench.merge import _branch_setup, merge_mode, pairwise_conflicts
from parbench.sandbox import HostWorkspace


def _workspace(files: dict[str, str]) -> tuple[HostWorkspace, str]:
    c = HostWorkspace("unused")
    Path(c.repo).mkdir(parents=True)
    Path(c.work).mkdir(parents=True)
    for p, text in files.items():
        (Path(c.repo) / p).write_text(text)
    c.started = True
    c.exec("git init -q && git config user.email t@t && git config user.name t && git add -A && git commit -qm base")
    return c, c.base_sha()


def _patch(c: HostWorkspace, base: str, path: str, text: str) -> str:
    c.sh(f"git checkout -q --detach {base}")
    (Path(c.repo) / path).write_text(text)
    d = c.diff_against(base)
    c.sh("git checkout -q -- . && git clean -fdq")
    return d


def test_llm_resolution_left_unstaged_counts_as_resolved():
    c, base = _workspace({"a.py": "x = 0\n"})
    try:
        patches = [("f1", [1], _patch(c, base, "a.py", "x = 1\n")), ("f2", [2], _patch(c, base, "a.py", "x = 2\n"))]
        _branch_setup(c, base, patches)
        assert pairwise_conflicts(c, base, ["f1", "f2"])[0]["conflict"]

        def resolver(cc, files, fids, log_dir):
            (Path(cc.repo) / "a.py").write_text("x = 3\n")  # markers removed, not staged, not committed
            return object()

        log = Path(c.work) / "merge"
        res, recs = merge_mode(c, base, patches, "llm", log, resolver)
        assert [s.outcome for s in res.steps] == ["merged", "resolved"]
        assert res.lost_features == [] and "+x = 3" in res.final_patch

        naive, _ = merge_mode(c, base, patches, "naive", log)
        assert naive.lost_features == [2] and "+x = 1" in naive.final_patch

        def aborter(cc, files, fids, log_dir):
            cc.exec("git merge --abort")
            return object()

        aborted, _ = merge_mode(c, base, patches, "llm", log, aborter)
        assert aborted.steps[1].outcome == "resolve_failed" and aborted.lost_features == [2]
    finally:
        c.remove()
