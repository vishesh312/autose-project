"""Harness adapter interface. One adapter per agent CLI."""

from __future__ import annotations

import json
import re
import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ModelSpec, Usage
from ..sandbox import WORK, Container

FILE_ARG_KEYS = ("file_path", "filePath", "path", "file", "filename", "AbsolutePath", "TargetFile", "notebook_path")


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    ok: bool | None = None
    ts: float | None = None

    @property
    def files(self) -> list[str]:
        out = []
        for k in FILE_ARG_KEYS:
            v = self.args.get(k)
            if isinstance(v, str) and v:
                out.append(v)
        return out

    @property
    def kind(self) -> str:
        """Coarse category used for 'repeated reading' / edit metrics."""
        n = self.name.lower()
        if any(s in n for s in ("web", "url", "fetch", "browser")):
            return "web"
        if any(s in n for s in ("read", "view", "cat", "grep", "glob", "search", "list", "ls", "find")):
            return "read"
        if any(s in n for s in ("edit", "write", "patch", "replace", "create", "apply")):
            return "edit"
        if any(s in n for s in ("bash", "shell", "command", "exec", "terminal")):
            return "shell"
        if n in ("task", "agent") or any(s in n for s in ("subagent", "delegate", "spawn")):
            return "subagent"
        return "other"


@dataclass
class ParsedRun:
    session_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    final_text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    num_turns: int | None = None
    asked_question: bool = False  # harness-level signal that the agent asked the user something
    error: str | None = None
    subagent_calls: int = 0


@dataclass
class RunOptions:
    subagents: bool = False
    max_turns: int | None = None
    timeout_s: int = 1800


class Harness(ABC):
    name: str = "base"
    supports_subagents: bool = False
    # Paths (relative to repo root) the harness may create that must not count as agent changes.
    repo_artifacts: list[str] = []
    # Model providers this harness can drive.
    providers: tuple[str, ...] = ()
    cost_is_cumulative = False  # reported cost already includes earlier resumed attempts
    usage_is_cumulative = False  # token usage is a session-level running total (take deltas across attempts)
    forward_env: list[str] = []
    host_capable = False  # adapter works with HostWorkspace (paths come from c.work / c.repo)
    host_mode = False  # True: run on the host in a temp clone (login cannot be carried into a container)
    auth_files: list[tuple[str, str]] = []

    def check_model(self, model: ModelSpec) -> None:
        if self.providers and model.provider not in self.providers:
            raise ValueError(f"{self.name} cannot use provider {model.provider!r} (model {model.id})")

    def setup(self, c: Container, model: ModelSpec, opts: RunOptions) -> dict[str, str]:
        """Write config files into the container; return env vars for the agent process."""
        return {}

    @abstractmethod
    def command(self, prompt_file: str, model: ModelSpec, opts: RunOptions, resume_session: str | None) -> str:
        """Shell command (run with cwd=/workspace/repo) that runs one headless turn."""

    @abstractmethod
    def parse(self, stdout: str, stderr: str) -> ParsedRun:
        ...

    def version_cmd(self) -> str:
        return f"{self.name} --version"

    # helpers --------------------------------------------------------
    @staticmethod
    def q(s: str) -> str:
        return shlex.quote(s)

    @staticmethod
    def prompt_arg(prompt_file: str) -> str:
        return f'"$(cat {shlex.quote(prompt_file)})"'

    @staticmethod
    def jsonl(stdout: str):
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    @staticmethod
    def write_json(c: Container, path: str, obj: Any) -> None:
        c.put_file(path, json.dumps(obj, indent=2))


QUESTION_PATTERNS = re.compile(
    r"(would you like|do you want|should i\b|shall i\b|let me know|please confirm|can you (clarify|confirm)|"
    r"which (option|approach) (would|do) you|before i proceed|want me to|how would you like)",
    re.I,
)


def looks_like_question(text: str) -> bool:
    tail = text.strip()[-600:]
    return bool(tail) and (tail.endswith("?") or bool(QUESTION_PATTERNS.search(tail)))




def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
