#!/usr/bin/env bash
# Check the host-mode agent sandbox (docs/sandboxing.md) on this machine. Prints PASS/FAIL per check.
# Uses the same code path as `sandbox: on` in an experiment config (sandbox_policy.wrap_host). No root needed.
#
#   scripts/sandbox_selftest.sh [MODEL_URL]     # default http://localhost:8000/v1/models (vLLM)
#
# The model server must be running for the "model endpoint reachable" check. Exit code 0 = all PASS.
set -u
cd "$(dirname "$0")/.."
URL="${1:-http://localhost:8000/v1/models}"
PY="${PYTHON:-}"
[ -z "$PY" ] && { [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=python3; }

echo "== host info (for the record)"
uname -sr
[ -r /sys/kernel/security/lsm ] && echo "LSMs: $(cat /sys/kernel/security/lsm)"
[ -r /proc/sys/kernel/apparmor_restrict_unprivileged_userns ] && \
  echo "apparmor_restrict_unprivileged_userns=$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns)"
command -v unshare >/dev/null && { unshare -rn true 2>/dev/null && echo "unshare -rn: works" || echo "unshare -rn: blocked"; }
command -v bwrap >/dev/null && echo "bwrap: $(command -v bwrap)" || echo "bwrap: not installed"

PYTHONPATH=src "$PY" - "$URL" <<'EOF'
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
from parbench.sandbox_policy import SandboxPolicy, _hostport, describe, wrap_host

url = sys.argv[1]
root = Path(tempfile.mkdtemp(prefix="parbench-sbxtest-"))
outside = Path(tempfile.mkdtemp(prefix="parbench-sbxtest-outside-"))
home_probe = Path.home() / ".parbench_sbx_selftest"
tmp_probe = Path("/tmp") / f"parbench_sbx_selftest_{os.getpid()}"
hidden = outside / "dataset"  # stands in for the CooperBench dataset (hide_gold)
hidden.mkdir()
(hidden / "feature.patch").write_text("gold")
pol = SandboxPolicy("on", [_hostport(url)], hide=[str(hidden)])
print("== mode")
info = describe(pol, host=True)
for k, v in info.items():
    print(f"  {k}: {v}")


def run(cmd):
    argv, env = wrap_host(["bash", "-c", cmd], dict(os.environ), root, pol)
    try:
        return subprocess.run(argv, env=env, cwd=root, capture_output=True, text=True, timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        return False


raw = "python3 -c \"import socket; socket.create_connection(('{}', {}), 8)\""
checks = [  # (name, command, should succeed)
    ("internet blocked: curl https://example.com (proxy env ignored)",
     "curl --noproxy '*' -sS -m 8 -o /dev/null https://example.com", False),
    ("internet blocked: raw TCP to 1.1.1.1:443", raw.format("1.1.1.1", 443), False),
    ("internet blocked: raw TCP to 1.1.1.1:80", raw.format("1.1.1.1", 80), False),
    (f"model endpoint reachable: {url}", f"curl --noproxy '*' -sS -m 8 -o /dev/null {url}", True),
    ("local test server works (bind port 0 + connect)",
     "python3 -c \"import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(); "
     "socket.create_connection(s.getsockname(), 5)\"", True),
    ("write inside workspace allowed", "echo x > inside.txt && mkdir d && mv inside.txt d/ && rm -r d", True),
    ("temp files (TMPDIR) allowed", "python3 -c 'import tempfile; tempfile.mkstemp()'", True),
    ("read of hidden dataset blocked (gold patch)", f"cat {hidden}/feature.patch", False),
    ("listing of hidden dataset blocked", f"ls {hidden}", False),
    ("read outside the hidden paths allowed", f"cat {outside}/keep && cat /etc/hosts >/dev/null", True),
    ("write outside workspace blocked", f"echo x > {outside}/f", False),
    ("delete outside workspace blocked", f"touch {outside}/keep 2>/dev/null; rm -f {outside}/keep", False),
    ("write in $HOME blocked", f"touch {home_probe}", False),
    ("write in /tmp blocked", f"touch {tmp_probe}", False),
]
(outside / "keep").write_text("x")  # target for the delete check, created outside the sandbox
failed = 0
print("== checks")
for name, cmd, want in checks:
    ok = run(cmd) == want
    failed += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
for p in (home_probe, tmp_probe):
    p.unlink(missing_ok=True)
shutil.rmtree(root, ignore_errors=True)
shutil.rmtree(outside, ignore_errors=True)
print(f"== {len(checks) - failed}/{len(checks)} PASS (mode {info['mode']})")
sys.exit(1 if failed else 0)
EOF
