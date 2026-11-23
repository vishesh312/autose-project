"""Agent sandboxing: no internet except the model endpoint, no writes outside the workspace.

Config `sandbox: off | on | require` (ExperimentConfig). `on` picks the strongest mode available and falls back
with a loud log line; `require` refuses to run unless both network and filesystem are enforced. Modes:

  docker          (off)  container on the default bridge: full internet; files outside the container untouched
  docker-egress   (on)   container on an `--internal` network (no route out, no DNS). Each allowed endpoint host is
                         mapped (/etc/hosts) to a tiny socat container that forwards only its ports.
  host-landlock   (on)   Linux host: Landlock, writes only under the workspace (+ XDG dirs the harness sets);
                         from ABI 4 TCP connect only to the model port(s) and the ephemeral range (local test servers)
  host-seatbelt   (on)   macOS host: sandbox-exec; writes only under the workspace; outgoing traffic only to loopback
  host-proxyenv   (on)   fallback: dead HTTP(S)_PROXY only (advisory; a tool can ignore it); files not enforced
  agy-native      (any)  agy runs on the host with its own `--sandbox` (see NATIVE); we add nothing
  host-none       (off)  host mode as before

Every run records `describe(...)` in run.json (`run.sandbox`). Tested results: docs/sandboxing.md.
"""

from __future__ import annotations

import functools
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

LEVELS = ("off", "on", "require")
PROXY_IMAGE = os.environ.get("PARBENCH_PROXY_IMAGE", "alpine/socat:latest")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
PROVIDER_ENDPOINTS = {  # used when a model has no base_url (UNVERIFIED: a harness may also call auth/telemetry hosts)
    "anthropic": "api.anthropic.com:443", "openai": "api.openai.com:443",
    "google": "generativelanguage.googleapis.com:443", "openrouter": "openrouter.ai:443",
}
NATIVE = {  # harnesses that enforce their own sandbox on the host (tested 2026-11-23, docs/sandboxing.md)
    "agy": "agy --sandbox: shell commands run under sandbox-exec with no network (not even localhost) and no writes "
           "to $HOME outside the workspace; writes to /tmp and $TMPDIR are allowed; file tools are limited to the "
           "workspace by --mode accept-edits; agy itself talks to Google",
}
LANDLOCK_PY = Path(__file__).with_name("landlock.py")
_announced: set[str] = set()


@dataclass
class SandboxPolicy:
    level: str = "off"
    allow: list[tuple[str, int]] = field(default_factory=list)  # (host, port) the agent may connect to
    writable: list[str] = field(default_factory=list)  # extra writable paths (host modes)
    native: str | None = None
    hide: list[str] = field(default_factory=list)  # paths host-mode agents must not read (gold patches, tests, results)
    hide_keep: list[str] = field(default_factory=list)  # readable exceptions inside them (parbench's own .venv)

    @property
    def enabled(self) -> bool:
        return self.level != "off"


def _hostport(s: str) -> tuple[str, int]:
    if "://" in s:
        u = urlparse(s)
        return u.hostname or "", u.port or (443 if u.scheme == "https" else 80)
    host, _, port = s.rpartition(":")
    return host, int(port)


def policy_for(cfg, harness, model) -> SandboxPolicy:
    level = getattr(cfg, "sandbox", "off") or "off"
    if level not in LEVELS:
        raise ValueError(f"sandbox must be one of {LEVELS}, got {level!r}")
    urls = [u for u in (model.base_url, model.anthropic_base_url) if u]
    if not urls and model.provider in PROVIDER_ENDPOINTS:
        urls = [PROVIDER_ENDPOINTS[model.provider]]
    allow = list(dict.fromkeys(_hostport(u) for u in [*urls, *getattr(cfg, "sandbox_allow", [])]))
    hide, keep = hidden_paths(cfg) if getattr(cfg, "hide_gold", True) else ([], [])
    return SandboxPolicy(level, allow, list(getattr(cfg, "sandbox_writable", [])), NATIVE.get(harness.name),
                         hide, keep)


def hidden_paths(cfg) -> tuple[list[str], list[str]]:
    """What a host-mode agent must not read: the dataset (feature.patch = gold, tests.patch = hidden tests), the
    whole parbench checkout (results/ of other runs, .env, external/, worktrees), and the temp dir that holds every
    host workspace, including grading clones with tests.patch applied (the agent's own workspace is re-allowed in
    wrap_host). parbench's .venv stays readable (its python may be on PATH)."""
    import tempfile

    from .config import ROOT

    hide = [str(cfg.dataset_path()), str(ROOT), tempfile.gettempdir()]
    git = ROOT / ".git"
    if git.is_file() and "/.git/" in git.read_text():  # ROOT is a git worktree: hide the main checkout too
        hide.append(git.read_text().split("gitdir:", 1)[-1].strip().split("/.git/")[0])
    return list(dict.fromkeys(os.path.realpath(p) for p in hide)), [str(ROOT / ".venv")]


def _announce(info: dict) -> None:
    line = (f"[parbench] SANDBOX MODE: {info['mode']} | network: {info['network']} | files: {info['files']}"
            + (f" | gold: {info['gold']}" if info.get("gold") else "")
            + (f" | {info['note']}" if info.get("note") else ""))
    if line not in _announced:
        _announced.add(line)
        print(line, file=sys.stderr, flush=True)


@functools.cache
def landlock_abi() -> int:
    if platform.system() != "Linux":
        return 0
    try:
        out = subprocess.run([sys.executable, str(LANDLOCK_PY), "--check"], capture_output=True, text=True, timeout=30)
        return int(out.stdout.strip() or 0)
    except Exception:
        return 0


@functools.cache
def _ephemeral_range() -> tuple[int, int]:
    try:
        lo, hi = Path("/proc/sys/net/ipv4/ip_local_port_range").read_text().split()
        return int(lo), int(hi)
    except Exception:
        return 32768, 60999


def describe(policy: SandboxPolicy | None, host: bool) -> dict:
    """The mode that is (or would be) active, as recorded in run.json. Raises under `require` if not enforced."""
    p = policy or SandboxPolicy()
    remote = sorted({f"{h}:{port}" for h, port in p.allow if h not in LOCAL_HOSTS})
    allow = [f"{h}:{port}" for h, port in p.allow]
    if not host:
        info = ({"mode": "docker-egress", "network": f"only {', '.join(allow) or 'nothing'}", "files": "container"}
                if p.enabled else {"mode": "docker", "network": "open", "files": "container"})
    elif p.native:
        info = {"mode": "agy-native", "network": "commands: none; agent process: open", "files": "workspace + temp",
                "note": p.native}
    elif not p.enabled:
        info = {"mode": "host-none", "network": "open", "files": "open"}
    elif platform.system() == "Linux" and landlock_abi() >= 1:
        v = landlock_abi()
        if v < 4:
            net = "advisory (dead HTTP_PROXY; Landlock ABI < 4 has no TCP rules)"
        elif remote:
            net = f"NOT enforced (remote endpoint {', '.join(remote)}: Landlock filters ports, not hosts)"
        else:
            lo, hi = _ephemeral_range()
            net = f"TCP connect only to ports {sorted({port for _, port in p.allow})} + {lo}-{hi}; UDP not covered"
        info = {"mode": "host-landlock", "network": net, "files": "workspace only", "landlock_abi": v}
    elif platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        net = (f"NOT enforced (remote endpoint {', '.join(remote)})" if remote else "loopback only")
        info = {"mode": "host-seatbelt", "network": net, "files": "workspace only"}
    else:
        info = {"mode": "host-proxyenv", "network": "advisory (dead HTTP_PROXY)", "files": "NOT enforced"}
    info["level"] = p.level
    info["allow"] = allow
    if not host:
        info["gold"] = "not in the container"
    elif p.native:
        info["gold"] = "NOT hidden (agy file tools read anywhere; check with `parbench audit-leak`)"
    elif p.hide and _read_guard():
        info["gold"] = f"hidden ({_read_guard()}): dataset, parbench checkout, other workspaces"
    else:
        info["gold"] = "NOT hidden" + ("" if p.hide else " (hide_gold: false)")
    if p.level == "require" and info["mode"] not in ("docker-egress", "agy-native") and (
            info["files"] == "NOT enforced" or info["network"].startswith(("NOT", "advisory"))):
        raise RuntimeError(f"sandbox: require, but only {info} is available here")
    _announce(info)
    return info


def record(cfg, harness, model) -> dict:
    """For runner.build_record: the sandbox mode this run used."""
    host = (harness.host_mode or harness.name in getattr(cfg, "host_harnesses", [])
            or bool(os.environ.get("PARBENCH_HOST_POOLS")))
    return describe(policy_for(cfg, harness, model), host)


# ------------------------------------------------------------------ host modes
def _read_guard() -> str | None:
    """The mechanism that can hide paths from a host-mode agent here, if any."""
    if platform.system() == "Linux" and landlock_abi() >= 1:
        return "landlock"
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    return None


def _hide_only(argv: list[str], env: dict[str, str], root: Path, policy: SandboxPolicy):
    """`sandbox: off` still hides the gold paths (reads only; writes and network unchanged)."""
    guard = _read_guard() if policy.hide else None
    if not guard:
        return argv, env
    tmp = root / "tmp"  # the real temp dir is hidden, so temp files go into the workspace
    tmp.mkdir(exist_ok=True)
    env = {**env, "TMPDIR": str(tmp), "TMP": str(tmp), "TEMP": str(tmp)}
    keep = [str(root), *policy.hide_keep, *policy.writable,
            *(v for k, v in env.items() if k.startswith("XDG_") and k.endswith("_HOME") and v)]
    if guard == "landlock":
        args = [sys.executable, str(LANDLOCK_PY)]
        for h in policy.hide:
            args += ["--deny-read", h]
        for k in keep:
            args += ["--keep-read", k]
        return [*args, "--", *argv], env
    return ["sandbox-exec", "-p", seatbelt_profile(None, False, policy.hide, keep), *argv], env


def wrap_host(argv: list[str], env: dict[str, str], root: Path, policy: SandboxPolicy | None):
    """Return (argv, env) to run `argv` confined to `root` according to the active host mode."""
    if policy is None or policy.native:  # agy: its shell already runs under sandbox-exec, which cannot nest (tested)
        return argv, env
    if not policy.enabled:
        return _hide_only(argv, env, root, policy)
    info = describe(policy, host=True)
    tmp = root / "tmp"
    tmp.mkdir(exist_ok=True)
    no_proxy = ",".join(sorted({"localhost", "127.0.0.1", "::1", *(h for h, _ in policy.allow)}))
    dead = "http://127.0.0.1:9"  # discard port: nothing listens, so cooperative tools fail fast
    env = {**env, "TMPDIR": str(tmp), "TMP": str(tmp), "TEMP": str(tmp),
           **{k: dead for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")},
           "NO_PROXY": no_proxy, "no_proxy": no_proxy}
    # XDG dirs the harness points outside the workspace (OpenCode 1.x shares ~/.cache) stay writable.
    writable = [str(root), *policy.writable,
                *(v for k, v in env.items() if k.startswith("XDG_") and k.endswith("_HOME") and v)]
    for w in writable:
        Path(w).mkdir(parents=True, exist_ok=True)
    if info["mode"] == "host-landlock":
        args = [sys.executable, str(LANDLOCK_PY)]
        for w in [*writable, "/dev/null", "/dev/zero", "/dev/full", "/dev/tty", "/dev/pts", "/dev/shm"]:
            args += ["--rw", w]
        for port in sorted({port for _, port in policy.allow}):
            args += ["--connect-port", str(port)]
        for h in policy.hide:
            args += ["--deny-read", h]
        for k in policy.hide_keep:
            args += ["--keep-read", k]
        lo, hi = _ephemeral_range()
        return [*args, "--connect-range", f"{lo}-{hi}", "--", *argv], env
    if info["mode"] == "host-seatbelt":
        return ["sandbox-exec", "-p", seatbelt_profile(writable, not info["network"].startswith("NOT"), policy.hide,
                                                      [*writable, *policy.hide_keep]), *argv], env
    return argv, env


def seatbelt_profile(writable: list[str] | None, loopback_only: bool, hide: list[str] = (),
                     keep: list[str] = ()) -> str:
    """Seatbelt rules: writes only under `writable` (None: writes unrestricted), no reads under `hide` except under
    `keep`. Later rules win, so the `keep` allowance comes after the `hide` denial."""
    def q(p: str) -> str:
        return '"' + os.path.realpath(p).replace("\\", "\\\\").replace('"', '\\"') + '"'

    subpaths = " ".join(f"(subpath {q(w)})" for w in writable or [])
    rules = ["(version 1)", "(allow default)"]
    if writable is not None:
        rules += ["(deny file-write*)",
                  f'(allow file-write* {subpaths} (literal "/dev/null") (literal "/dev/zero") '
                  '(literal "/dev/dtracehelper") (regex #"^/dev/tty") (regex #"^/dev/fd/"))']
    if hide:
        rules.append("(deny file-read* " + " ".join(f"(subpath {q(h)})" for h in hide) + ")")
        if keep:
            rules.append("(allow file-read* " + " ".join(f"(subpath {q(k)})" for k in keep) + ")")
    if loopback_only:
        rules += ["(deny network-outbound)", '(allow network-outbound (remote ip "localhost:*"))',
                  f"(allow network-outbound {subpaths})"]  # unix sockets inside the workspace
    return "\n".join(rules)


# ------------------------------------------------------------------ docker mode
class DockerEgress:
    """An `--internal` network for one agent container, plus one socat forwarder per allowed host."""

    def __init__(self, name: str, allow: list[tuple[str, int]], docker):
        self.name, self.allow, self._docker = name, allow, docker
        self.net = f"{name}-net"
        self.proxies: list[str] = []
        self.created = False

    def start(self) -> list[str]:
        """Create network + forwarders; return the `docker run` args for the agent container."""
        from .sandbox import ensure_image

        by_host: dict[str, list[int]] = {}
        for h, port in self.allow:
            by_host.setdefault(h, []).append(port)
        if by_host:
            ensure_image(PROXY_IMAGE)
        self._docker("network", "create", "--internal", "--label", "parbench=1", self.net)
        self.created = True
        args = ["--network", self.net]
        for i, (h, ports) in enumerate(by_host.items()):
            target = "host.docker.internal" if h in LOCAL_HOSTS else h
            script = " ".join(f"socat TCP-LISTEN:{p},fork,reuseaddr TCP:{target}:{p} &" for p in ports) + " wait"
            px = f"{self.name}-px{i}"
            self._docker("run", "-d", "--name", px, "--label", "parbench=1", "--label", "parbench.role=egress",
                         "--add-host", "host.docker.internal:host-gateway", "--entrypoint", "sh", PROXY_IMAGE,
                         "-c", script)
            self.proxies.append(px)
            self._docker("network", "connect", self.net, px)
            ip = self._docker("inspect", "-f", f'{{{{(index .NetworkSettings.Networks "{self.net}").IPAddress}}}}',
                              px).stdout.strip()
            if h not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):  # those mean the container itself
                args += ["--add-host", f"{h}:{ip}"]
        return args

    def remove(self) -> None:
        if self.proxies:
            self._docker("rm", "-f", *self.proxies, check=False)
            self.proxies = []
        if self.created:
            self._docker("network", "rm", self.net, check=False)
            self.created = False
