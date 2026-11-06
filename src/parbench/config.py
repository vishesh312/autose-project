"""Model registry, experiment config and token-usage accounting."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- usage
@dataclass
class Usage:
    """Normalised token counts. `input` counts ALL prompt tokens (cached ones included);
    `cached_input` is the subset served from cache. Adapters convert harness-specific
    conventions (e.g. Anthropic reports cache reads separately from input_tokens)."""

    input: int = 0
    cached_input: int = 0
    cache_write: int = 0
    output: int = 0
    reasoning: int = 0
    cost_reported: float | None = None  # $ as reported by the harness itself, if any
    calls: int = 0  # number of model calls / steps observed

    def __add__(self, o: "Usage") -> "Usage":
        cr = None
        if self.cost_reported is not None or o.cost_reported is not None:
            cr = (self.cost_reported or 0.0) + (o.cost_reported or 0.0)
        return Usage(
            self.input + o.input,
            self.cached_input + o.cached_input,
            self.cache_write + o.cache_write,
            self.output + o.output,
            self.reasoning + o.reasoning,
            cr,
            self.calls + o.calls,
        )

    def __sub__(self, o: "Usage") -> "Usage":
        cr = None if self.cost_reported is None else self.cost_reported - (o.cost_reported or 0.0)
        return Usage(self.input - o.input, self.cached_input - o.cached_input, self.cache_write - o.cache_write,
                     self.output - o.output, self.reasoning - o.reasoning, cr, self.calls - o.calls)

    @property
    def total(self) -> int:
        return self.input + self.output

    def to_json(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- models
@dataclass
class ModelSpec:
    """One model as the harnesses should see it. See configs/models.yaml for fields."""

    id: str
    model: str  # name passed to the harness / server
    provider: str  # openai_compat | anthropic | openai | google | antigravity | openrouter
    base_url: str | None = None  # OpenAI-compatible /v1 URL (as reachable from inside containers)
    anthropic_base_url: str | None = None  # Anthropic-compatible URL (for Claude Code on local servers)
    responses_api: bool = False  # server supports /v1/responses (Codex needs it)
    api_key_env: str | None = None  # host env var holding the key; forwarded into containers
    context: int = 65536
    max_output: int = 8192
    reasoning_effort: str | None = None
    temperature: float | None = None
    # $ per 1M tokens. For self-hosted models use a reference API price (e.g. OpenRouter) so cost is comparable.
    price: dict[str, float] = field(default_factory=dict)
    harness_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: str = ""

    def list_cost(self, u: Usage) -> float | None:
        if not self.price:
            return None
        p_in, p_cached = self.price.get("input", 0.0), self.price.get("cached_input", self.price.get("input", 0.0))
        p_out, p_cw = self.price.get("output", 0.0), self.price.get("cache_write", self.price.get("input", 0.0))
        uncached = max(u.input - u.cached_input, 0)
        return (uncached * p_in + u.cached_input * p_cached + u.cache_write * p_cw + (u.output) * p_out) / 1e6

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None


def load_models(path: Path | None = None) -> dict[str, ModelSpec]:
    path = path or ROOT / "configs" / "models.yaml"
    raw = yaml.safe_load(path.read_text())["models"]
    return {mid: ModelSpec(id=mid, **spec) for mid, spec in raw.items()}


# ---------------------------------------------------------------- experiments
@dataclass
class MergeConfig:
    # Each mode produces its own final tree and gets graded: naive (git merge, skip conflicting branch),
    # union (git union merge driver), llm (git merge; same harness+model resolves conflict markers).
    modes: list[str] = field(default_factory=lambda: ["naive", "union", "llm"])


@dataclass
class ExperimentConfig:
    name: str
    dataset: str = "external/CooperBench/dataset"
    pools: list[str] | None = None  # pool ids or repo names; None = all
    k: list[int] = field(default_factory=lambda: [2])
    bundles_per_pool: int | None = 1
    seed: int = 0
    strategies: list[str] = field(default_factory=lambda: ["S0", "S1"])
    harnesses: list[str] = field(default_factory=lambda: ["opencode"])
    models: list[str] = field(default_factory=list)
    repeats: int = 1
    agent_timeout_s: int = 1800
    max_turns: int | None = 100
    max_nudges: int = 2
    max_parallel_runs: int = 1  # >1 speeds up pass-rate runs but makes timing metrics unfair
    s0_parallel: int = 1  # S0 runs k isolated agents; how many at once
    grade_parallel: int = 2
    merge: MergeConfig = field(default_factory=MergeConfig)
    prompt_variants: dict[str, str] = field(default_factory=dict)  # strategy -> prompt template name
    container_memory: str | None = None
    container_cpus: str | None = None
    forward_env: list[str] = field(default_factory=list)  # extra host env vars to pass into agent containers
    copy_auth_files: bool = False  # copy harness login files (e.g. ~/.codex/auth.json) into containers
    agent_image_suffix: str = "parbench-agent"
    results_dir: str = "results"

    @classmethod
    def load(cls, path: Path) -> "ExperimentConfig":
        raw = yaml.safe_load(Path(path).read_text())
        if "merge" in raw:
            raw["merge"] = MergeConfig(**raw["merge"])
        return cls(**raw)

    def dataset_path(self) -> Path:
        p = Path(self.dataset)
        return p if p.is_absolute() else ROOT / p


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (KEY=VALUE lines) so API keys don't need exporting by hand."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
