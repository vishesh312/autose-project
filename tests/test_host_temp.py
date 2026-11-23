"""HostWorkspace never leaks its temp clone, and `cleanup --host-temp` only removes old, ownerless clones."""

import os
import time

import pytest

from parbench import sandbox
from parbench.sandbox import HostWorkspace, cleanup_host_temp


def test_failed_start_removes_temp_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PARBENCH_HOST_POOLS", str(tmp_path / "missing"))
    ws = HostWorkspace("hostpool:nope/task1")
    assert ws.root.exists()
    with pytest.raises(Exception):
        ws.start()
    assert not ws.root.exists()


def _clone(tmp, name, age_h, pid=None):
    d = tmp / name
    d.mkdir()
    if pid is not None:
        (d / "owner.pid").write_text(str(pid))
    t = time.time() - age_h * 3600
    os.utime(d, (t, t))
    return d


def test_cleanup_host_temp(tmp_path):
    old = _clone(tmp_path, "parbench-host-old", 30)
    dead = _clone(tmp_path, "parbench-host-dead", 30, pid=2**22 + 12345)  # no such process
    live = _clone(tmp_path, "parbench-host-live", 30, pid=os.getpid())
    new = _clone(tmp_path, "parbench-host-new", 1)
    other = _clone(tmp_path, "something-else", 30)
    removed = cleanup_host_temp(24, tmpdir=str(tmp_path), jobs=[])
    assert sorted(removed) == sorted([old, dead])
    assert live.exists() and new.exists() and other.exists()


def test_cleanup_refuses_while_jobs_run(tmp_path):
    d = _clone(tmp_path, "parbench-host-old", 30)
    with pytest.raises(RuntimeError):
        cleanup_host_temp(24, tmpdir=str(tmp_path), jobs=["parbench run configs/x.yaml"])
    assert d.exists()


def test_job_detection_ignores_unrelated(monkeypatch):
    class R:
        stdout = ("  1 /sbin/launchd\n 42 /x/.venv/bin/python /x/.venv/bin/parbench run cfg.yaml\n"
                  " 43 vim notes-about-parbench run\n 44 /usr/bin/python3 -m parbench cleanup --host-temp 1\n")
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *a, **k: R)
    assert sandbox._parbench_jobs() == ["/x/.venv/bin/python /x/.venv/bin/parbench run cfg.yaml"]
