"""Host-mode agents cannot read the gold patches / hidden tests (or other workspaces), but their own workspace works.

The read-allow-list logic for Landlock is checked anywhere; the real enforcement runs only where the mechanism
exists (seatbelt on macOS, Landlock on Linux)."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from parbench.config import ROOT, ExperimentConfig
from parbench.landlock import read_allow_list
from parbench.sandbox import HostWorkspace
from parbench.sandbox_policy import SandboxPolicy, _read_guard, hidden_paths, wrap_host


def test_read_allow_list(tmp_path):
    (tmp_path / "proj" / "dataset" / "t1").mkdir(parents=True)
    (tmp_path / "proj" / "src").mkdir()
    (tmp_path / "proj" / "README").write_text("x")
    (tmp_path / "other").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "proj" / "dataset")
    (tmp_path / "uplink").symlink_to(tmp_path / "proj")
    ds = str(tmp_path / "proj" / "dataset")
    allowed = read_allow_list([ds], [ds + "/t1"])
    real = os.path.realpath(tmp_path)
    assert os.path.join(real, "proj", "src") in allowed and os.path.join(real, "other") in allowed
    assert os.path.join(real, "proj", "README") in allowed
    assert not any(p.endswith(("/link", "/uplink")) or p == os.path.join(real, "proj") for p in allowed)
    assert not any(p.startswith(os.path.realpath(ds)) for p in allowed[:-1]) and allowed[-1] == ds + "/t1"


def test_audit_flags_gold_access_and_shell_network():
    from parbench.report import scan_calls

    calls = [
        {"name": "read", "kind": "read", "args": {"filePath": "/x/external/CooperBench/dataset/t/feature1/feature.patch"}},
        {"name": "bash", "kind": "shell", "args": {"command": "find / -name tests.patch"}},
        {"name": "bash", "kind": "shell", "args": {"command": "curl -s https://github.com/pallets/click/pull/2800"}},
        {"name": "run_command", "kind": "shell", "args": {"CommandLine": "pip download click"}},
        {"name": "bash", "kind": "shell", "args": {"command": "python -m pytest tests/test_core.py"}},
        {"name": "bash", "kind": "shell", "args": {"command": "curl -s localhost:8000/v1/models"}},
        {"name": "edit", "kind": "edit", "args": {"filePath": "src/click/core.py"}},
    ]
    leaks, net = scan_calls(calls)
    assert len(leaks) == 2 and len(net) == 3  # local curl is still a network attempt; pytest and edits are not


def test_hidden_paths_cover_dataset_checkout_and_temp():
    hide, keep = hidden_paths(ExperimentConfig(name="x"))
    assert os.path.realpath(ROOT) in hide and os.path.realpath(tempfile.gettempdir()) in hide
    assert keep == [str(ROOT / ".venv")]


@pytest.mark.skipif(_read_guard() is None, reason="no seatbelt/Landlock here")
def test_agent_cannot_read_hidden_paths(tmp_path):
    secret_dir = tmp_path / "dataset"
    secret_dir.mkdir()
    (secret_dir / "feature.patch").write_text("GOLD")
    ws = HostWorkspace("unused")
    try:
        (Path(ws.repo)).mkdir(parents=True)
        (Path(ws.repo) / "a.txt").write_text("mine")
        other = Path(tempfile.mkdtemp(prefix="parbench-host-"))  # another run's workspace
        (other / "tests.patch").write_text("HIDDEN")
        pol = SandboxPolicy("off", hide=[str(secret_dir), os.path.realpath(tempfile.gettempdir())])

        def run(cmd):
            argv, env = wrap_host(["bash", "-c", cmd], {"PATH": os.environ["PATH"]}, ws.root, pol)
            return subprocess.run(argv, env=env, cwd=ws.repo, capture_output=True, text=True, timeout=60)

        assert run(f"cat {secret_dir}/feature.patch").returncode != 0
        assert run(f"ls {secret_dir}").returncode != 0
        assert run(f"cat {other}/tests.patch").returncode != 0
        r = run("cat a.txt && echo new > b.txt && cat b.txt && git --version && python3 -c 'import tempfile; "
                "f = tempfile.NamedTemporaryFile(); f.write(b\"x\"); f.flush(); print(open(f.name).read())'")
        assert r.returncode == 0, r.stderr
        assert r.stdout.startswith("minenew\n")
    finally:
        ws.remove()
        import shutil

        shutil.rmtree(other, ignore_errors=True)
