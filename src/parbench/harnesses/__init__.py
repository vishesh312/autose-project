from __future__ import annotations

from .base import Harness
from .cli_agents import AgyHarness, ClaudeHarness, CodexHarness, GeminiHarness, OpenCodeHarness, PiHarness

_REGISTRY: dict[str, type[Harness]] = {
    "opencode": OpenCodeHarness,
    "pi": PiHarness,
    "claude": ClaudeHarness,
    "codex": CodexHarness,
    "agy": AgyHarness,
    "gemini": GeminiHarness,
}


def get_harness(name: str) -> Harness:
    if name not in _REGISTRY:
        raise KeyError(f"unknown harness {name!r}; choices: {sorted(_REGISTRY)}")
    return _REGISTRY[name]()


def all_harnesses() -> list[str]:
    return sorted(_REGISTRY)
