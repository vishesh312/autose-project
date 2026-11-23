"""Relaunch redoes invalid (quota/capacity) runs, keeps valid ones, and moves old outputs to _prev/."""

import json

from parbench.report import report
from parbench.runner import is_done, prepare_run_dir


def _run(d, valid):
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"valid": valid}))
    (d / "agents").mkdir()
    return d


def test_is_done(tmp_path):
    assert not is_done(tmp_path / "missing")
    assert is_done(_run(tmp_path / "ok", True))
    bad = _run(tmp_path / "bad", False)
    assert not is_done(bad)
    assert is_done(bad, retry_invalid=False)
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "run.json").write_text("{}")  # runs from before the `valid` field count as valid
    assert is_done(tmp_path / "old")


def test_invalid_outputs_moved_to_prev(tmp_path):
    d = _run(tmp_path / "r", False)
    prepare_run_dir(d)
    assert sorted(p.name for p in d.iterdir()) == ["_prev"]
    (prev,) = (d / "_prev").iterdir()
    assert (prev / "run.json").exists() and (prev / "agents").is_dir()
    (d / "error.txt").write_text("x")  # a second retry in the same second must not collide
    prepare_run_dir(d)
    assert len(list((d / "_prev").iterdir())) == 2


def test_report_excludes_invalid_and_prev(tmp_path):
    d = _run(tmp_path / "r", False)
    prepare_run_dir(d)
    assert report(tmp_path).startswith("no finished runs")
