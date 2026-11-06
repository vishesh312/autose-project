"""Thin wrapper over the `docker` CLI: one container per agent / merge step / grading step."""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO = "/workspace/repo"
WORK = "/parbench"  # scratch dir inside the container (prompts, harness output); outside the repo


@dataclass
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    started: float
    ended: float
    timed_out: bool = False

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


def _docker(*args: str, timeout: float | None = None, check: bool = True, input: str | None = None):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=check, input=input
    )


def image_exists(image: str) -> bool:
    return _docker("image", "inspect", image, check=False).returncode == 0


def ensure_image(image: str) -> None:
    if not image_exists(image):
        subprocess.run(["docker", "pull", image], check=True)


class Container:
    """A long-lived container (`sleep infinity`) that we `docker exec` into."""

    def __init__(
        self,
        image: str,
        *,
        name: str | None = None,
        env: dict[str, str] | None = None,
        network: str | None = None,
        memory: str | None = None,
        cpus: str | None = None,
        labels: dict[str, str] | None = None,
    ):
        self.image = image
        self.name = name or f"parbench-{uuid.uuid4().hex[:10]}"
        self.env = env or {}
        self.network = network
        self.memory = memory
        self.cpus = cpus
        self.labels = {"parbench": "1", **(labels or {})}
        self.started = False

    # -- lifecycle -------------------------------------------------------
    def start(self) -> "Container":
        args = ["run", "-d", "--name", self.name, "--entrypoint", "", "-w", REPO]
        if platform.system() == "Linux":
            # Docker Desktop provides host.docker.internal; plain Linux docker needs this mapping.
            args += ["--add-host", "host.docker.internal:host-gateway"]
        if self.network:
            args += ["--network", self.network]
        if self.memory:
            args += ["--memory", self.memory]
        if self.cpus:
            args += ["--cpus", self.cpus]
        for k, v in self.labels.items():
            args += ["--label", f"{k}={v}"]
        for k, v in self.env.items():
            args += ["-e", f"{k}={v}"]
        args += [self.image, "sleep", "infinity"]
        _docker(*args)
        self.started = True
        self.exec(f"mkdir -p {WORK}")
        return self

    def remove(self) -> None:
        if self.started:
            _docker("rm", "-f", self.name, check=False)
            self.started = False

    def __enter__(self) -> "Container":
        return self.start()

    def __exit__(self, *exc) -> None:
        if os.environ.get("PARBENCH_KEEP_CONTAINERS") != "1":
            self.remove()

    # -- exec ------------------------------------------------------------
    def exec(
        self,
        cmd: str,
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        workdir: str = REPO,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
    ) -> ExecResult:
        """Run `bash -c cmd` in the container. A timeout kills the in-container process too."""
        inner = cmd
        if timeout:
            # `timeout` exists in coreutils (debian) and busybox (alpine). -k: SIGKILL 10s after SIGTERM.
            inner = f"timeout -k 10 {int(timeout)} bash -c {shlex.quote(cmd)}"
        args = ["docker", "exec", "-w", workdir]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        args += [self.name, "bash", "-c", inner]
        started = time.time()
        out_f = open(stdout_path, "w") if stdout_path else None
        err_f = open(stderr_path, "w") if stderr_path else None
        try:
            proc = subprocess.run(
                args,
                stdout=out_f or subprocess.PIPE,
                stderr=err_f or subprocess.PIPE,
                text=True,
                timeout=(timeout + 60) if timeout else None,
            )
            rc, timed_out = proc.returncode, proc.returncode == 124
            stdout = proc.stdout if out_f is None else ""
            stderr = proc.stderr if err_f is None else ""
        except subprocess.TimeoutExpired:
            rc, timed_out, stdout, stderr = 124, True, "", "host-side timeout"
        finally:
            for f in (out_f, err_f):
                if f:
                    f.close()
        if stdout_path:
            stdout = Path(stdout_path).read_text(errors="replace")
        if stderr_path:
            stderr = Path(stderr_path).read_text(errors="replace")
        return ExecResult(rc, stdout, stderr, started, time.time(), timed_out)

    def sh(self, cmd: str, **kw) -> str:
        """exec and raise on failure; return stdout."""
        r = self.exec(cmd, **kw)
        if r.returncode != 0:
            raise RuntimeError(f"[{self.name}] command failed ({r.returncode}): {cmd}\n{r.output[-2000:]}")
        return r.stdout

    # -- files -----------------------------------------------------------
    def put_file(self, container_path: str, content: str | bytes, mode: str | None = None) -> None:
        """Copy content in via `docker cp` (no argv size limits, unlike echo-into-bash)."""
        data = content.encode() if isinstance(content, str) else content
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            parent = os.path.dirname(container_path)
            self.exec(f"mkdir -p {shlex.quote(parent)}")
            _docker("cp", tmp_path, f"{self.name}:{container_path}")
            if mode:
                self.exec(f"chmod {mode} {shlex.quote(container_path)}")
        finally:
            os.unlink(tmp_path)

    def put_path(self, host_path: Path, container_path: str) -> None:
        self.exec(f"mkdir -p {shlex.quote(os.path.dirname(container_path))}")
        _docker("cp", str(host_path), f"{self.name}:{container_path}")

    def get_file(self, container_path: str) -> str:
        r = self.exec(f"cat {shlex.quote(container_path)}")
        return r.stdout if r.returncode == 0 else ""

    # -- repo helpers ----------------------------------------------------
    def base_sha(self) -> str:
        return self.sh("git rev-parse HEAD").strip()

    def scrub_history(self) -> None:
        """Remove refs to commits after the base (CooperBench images clone full upstream history).

        Ported from CooperBench `GitConnector._detach_upstream` (MIT). History before the base is kept.
        """
        self.exec(
            "git remote remove origin 2>/dev/null || true; "
            "git for-each-ref --format='%(refname)' refs/remotes | xargs -r -n1 git update-ref -d 2>/dev/null || true; "
            "git tag -l | xargs -r git tag -d >/dev/null 2>&1 || true; "
            "git for-each-ref --format='%(refname:short)' refs/heads | xargs -r -n1 git branch -D >/dev/null 2>&1 || true; "
            "git stash clear 2>/dev/null || true; "
            "git reflog expire --expire=now --all >/dev/null 2>&1; git gc --prune=now --quiet >/dev/null 2>&1 || true",
            timeout=600,
        )
        self.exec(
            "git config --global user.email parbench@local && git config --global user.name parbench "
            "&& git config --global --add safe.directory '*'"
        )

    def diff_against(self, base_sha: str, exclude: list[str] | None = None) -> str:
        """All changes (tracked + untracked, binary-safe) vs base, without disturbing the working tree."""
        excludes = " ".join(shlex.quote(f":(exclude){p}") for p in (exclude or []))
        # Use a throwaway index so we never touch the agent's own index/staging.
        cmd = (
            f"export GIT_INDEX_FILE={WORK}/diff.index; rm -f $GIT_INDEX_FILE; "
            f"git read-tree {base_sha} && git add -A -- . {excludes} && "
            f"git diff --cached --binary {base_sha} -- . {excludes}"
        )
        r = self.exec(cmd, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"diff failed: {r.stderr[-1000:]}")
        return r.stdout


def cleanup_all() -> None:
    """Remove every container we started (label parbench=1)."""
    ids = _docker("ps", "-aq", "--filter", "label=parbench=1", check=False).stdout.split()
    if ids:
        _docker("rm", "-f", *ids, check=False)
