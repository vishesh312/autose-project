"""Antigravity (`agy`) accounts: one profile (a HOME directory) per account, chosen per agent process.

`agy` keeps its login in the macOS keychain item service "gemini" / account "antigravity", in the *default*
keychain, which macOS looks up under $HOME/Library/Keychains. So `HOME=<profile> agy ...` uses the login stored
in <profile>/Library/Keychains/login.keychain-db and nothing else (verified 2026-11-23: a scratch HOME gets
"Please sign in", and keychain writes under it do not touch your real keychain list). Parallel agents on
different accounts therefore don't interfere. `scripts/agy_login_account.sh N` logs account N into profile N.

The user asked (2026-11-23) to cycle through their own 3 accounts. Policy: every new agent takes the first
account that is not marked exhausted; on a quota error (429 / RESOURCE_EXHAUSTED) that account is marked
exhausted (a file under ~/.parbench/agy_exhausted/, so all parbench processes see it) and the agent moves to the next
one. Accounts are identified by their 1-based position in the list (never by email).
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import yaml

from .config import ROOT

CONFIG = ROOT / "configs" / "agy_accounts.yaml"
QUOTA = re.compile(r"RESOURCE_EXHAUSTED|quota reached|\b429\b", re.I)  # per-account; 503 "No capacity" is not
NOT_SIGNED_IN = re.compile(r"Authentication required|authentication failed|not logged into Antigravity|Please sign in", re.I)
DEFAULT_EXHAUSTED_S = 30 * 60
STATE = Path.home() / ".parbench" / "agy_exhausted"  # one file per profile: unix time it is usable again


def profiles() -> list[Path]:
    """Account profile dirs, in order. `PARBENCH_AGY_ACCOUNTS` (os.pathsep-separated) overrides the config."""
    env = os.environ.get("PARBENCH_AGY_ACCOUNTS")
    if env:
        items = [p for p in env.split(os.pathsep) if p]
    elif CONFIG.exists():
        items = (yaml.safe_load(CONFIG.read_text()) or {}).get("accounts") or ["~"]
    else:
        items = ["~"]
    return [Path(os.path.expanduser(str(p))) for p in items]


def _keychain(p: Path) -> Path:
    return p / "Library" / "Keychains" / "login.keychain-db"


def _signed_in(p: Path) -> bool:
    """Your normal HOME, or a profile whose keychain holds agy's login item (checked without reading it)."""
    if p.resolve() == Path.home().resolve():
        return True
    kc = _keychain(p)
    return kc.exists() and subprocess.run(["security", "find-generic-password", "-s", "gemini", "-a", "antigravity",
                                           str(kc)], capture_output=True, timeout=30).returncode == 0


def _mark(p: Path) -> Path:
    return STATE / str(p.resolve()).strip("/").replace("/", "_")


def _until(p: Path) -> float:
    try:
        return float(_mark(p).read_text())
    except (OSError, ValueError):
        return 0.0


def pick(exclude: int | None = None) -> int:
    """First account not marked exhausted (skipping `exclude`); if all are, the one that frees up first.
    Profiles without a login (scripts/agy_login_account.sh) are skipped: agy -p would wait 60 s for a sign-in."""
    ps, now = profiles(), time.time()
    order = [i for i in range(len(ps)) if i != exclude and _signed_in(ps[i])]
    order = order or [0]
    free = [i for i in order if _until(ps[i]) <= now]
    return free[0] if free else min(order, key=lambda i: _until(ps[i]))


def mark_exhausted(idx: int, seconds: int | None) -> None:
    mark = _mark(profiles()[idx])
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = mark.with_name(f"{mark.name}.{os.getpid()}")
    tmp.write_text(str(time.time() + (seconds or DEFAULT_EXHAUSTED_S)))
    os.replace(tmp, mark)


def on_error(idx: int, error: str | None) -> int | None:
    """After a quota or sign-in error on account `idx`: mark it, return a free other account (None = stay+wait)."""
    ps = profiles()
    if not error or len(ps) < 2 or idx >= len(ps):
        return None
    if QUOTA.search(error):
        m = re.search(r"resets? in (?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?", error, re.I)
        h, mi, s = (int(x or 0) for x in (m.groups() if m else (0, 0, 0)))
        mark_exhausted(idx, h * 3600 + mi * 60 + s or None)
    elif NOT_SIGNED_IN.search(error):
        mark_exhausted(idx, 24 * 3600)
    else:
        return None
    new = pick(exclude=idx)
    return new if _until(ps[new]) <= time.time() else None


def env_for(idx: int) -> dict[str, str]:
    """Env for an agy process on account `idx`: HOME=<profile> (nothing for your normal HOME)."""
    p = profiles()[idx]
    env = {"PARBENCH_AGY_ACCOUNT": str(idx + 1)}  # 1-based, as in the config file and the login script
    if p.resolve() == Path.home().resolve():
        return env
    kc = _keychain(p)
    if kc.exists():  # profile keychains have an empty password; unlock so `security` never shows a dialog
        subprocess.run(["security", "unlock-keychain", "-p", "", str(kc)], env={**os.environ, "HOME": str(p)},
                       capture_output=True, timeout=30)
    return {**env, "HOME": str(p)}
