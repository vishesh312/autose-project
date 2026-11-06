"""Orchestration strategies. Strategy spec strings:  ID[@template][+extra...]

  S0   isolated: each task alone in a fresh container (k=1 reference for retention)
  S1   one agent gets all k tasks in one prompt, subagents disabled
  S2   one agent per task in parallel (own container each) -> merge (naive / union / llm resolver)
  S4   all tasks in one prompt, harness-native subagents enabled; the harness splits & integrates itself

  @template  overrides the prompt template, e.g. S4@harness_native_worktrees, S4@harness_native_encourage
  +extra     appends a prompt snippet, e.g. S2+plan_first
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .agent_runner import AgentRecord, run_agent
from .config import ExperimentConfig, ModelSpec
from .dataset import Bundle, Feature
from .harnesses.base import Harness, RunOptions
from .merge import _branch_setup, merge_mode, overlap_lines, pairwise_conflicts
from . import prompts
from .sandbox import Container


@dataclass
class StrategySpec:
    id: str
    template: str | None = None
    extras: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, s: str) -> "StrategySpec":
        head, *extras = s.split("+")
        sid, _, tmpl = head.partition("@")
        return cls(sid, tmpl or None, extras)

    @property
    def label(self) -> str:
        return self.id + (f"@{self.template}" if self.template else "") + "".join(f"+{e}" for e in self.extras)


@dataclass
class RunContext:
    bundle: Bundle
    harness: Harness
    model: ModelSpec
    cfg: ExperimentConfig
    run_dir: Path
    agent_image: str
    env: dict[str, str]
    auth_files: list[tuple[Path, str]]


@dataclass
class StrategyResult:
    agents: list[AgentRecord] = field(default_factory=list)
    # (agent name, feature ids, that agent's own diff vs base)
    worker_patches: list[tuple[str, list[int], str]] = field(default_factory=list)
    finals: dict[str, str] = field(default_factory=dict)  # label -> final diff to grade on all k features
    merge: dict | None = None
    t_start: float = 0.0
    t_end: float = 0.0
    setup_s: float = 0.0


# ----------------------------------------------------------------- helpers
def _container(ctx: RunContext, role: str) -> tuple[Container, str]:
    c = Container(
        ctx.agent_image,
        env=ctx.env,
        memory=ctx.cfg.container_memory,
        cpus=ctx.cfg.container_cpus,
        labels={"parbench.role": role, "parbench.run": ctx.run_dir.name[:60]},
    ).start()
    c.scrub_history()
    for host, dest in ctx.auth_files:
        c.put_path(host, dest)
    return c, c.base_sha()


def _opts(ctx: RunContext, subagents: bool) -> RunOptions:
    return RunOptions(subagents=subagents, max_turns=ctx.cfg.max_turns, timeout_s=ctx.cfg.agent_timeout_s)


def _agent(ctx, c, base, prompt, *, agent_id, role, fids, subagents=False) -> AgentRecord:
    rec = run_agent(
        c, ctx.harness, ctx.model, prompt, _opts(ctx, subagents), ctx.run_dir / "agents" / agent_id,
        agent_id=agent_id, role=role, feature_ids=fids, max_nudges=ctx.cfg.max_nudges, base_sha=base,
    )
    return rec


def _collect(ctx, c, base, rec: AgentRecord) -> str:
    from .merge import patch_files, patch_line_count

    patch = c.diff_against(base, exclude=ctx.harness.repo_artifacts)
    (ctx.run_dir / "agents" / rec.agent_id / "patch.diff").write_text(patch)
    rec.patch_lines, rec.patch_files = patch_line_count(patch), patch_files(patch)
    return patch


def _keep() -> bool:
    import os

    return os.environ.get("PARBENCH_KEEP_CONTAINERS") == "1"


# ----------------------------------------------------------------- strategies
def run_single_session(ctx: RunContext, spec: StrategySpec, *, subagents: bool, default_tmpl: str) -> StrategyResult:
    """S1 and S4: one container, one session, all k tasks."""
    res = StrategyResult()
    t0 = time.time()
    c, base = _container(ctx, spec.id)
    try:
        res.setup_s = time.time() - t0
        prompt = prompts.multi_task(ctx.bundle.features, spec.template or default_tmpl,
                                    extra=spec.extras[0] if spec.extras else None)
        res.t_start = time.time()
        rec = _agent(ctx, c, base, prompt, agent_id="solo", role="solo", fids=ctx.bundle.feature_ids,
                     subagents=subagents)
        patch = _collect(ctx, c, base, rec)
        res.t_end = time.time()
        res.agents.append(rec)
        res.worker_patches.append(("solo", ctx.bundle.feature_ids, patch))
        res.finals["final"] = patch
    finally:
        if not _keep():
            c.remove()
    return res


def run_s0(ctx: RunContext, spec: StrategySpec) -> StrategyResult:
    res = StrategyResult()

    def one(f: Feature):
        c, base = _container(ctx, "S0")
        try:
            prompt = prompts.single_task(f, extra=spec.extras[0] if spec.extras else None)
            rec = _agent(ctx, c, base, prompt, agent_id=f"f{f.fid}", role="worker", fids=[f.fid])
            return rec, _collect(ctx, c, base, rec)
        finally:
            if not _keep():
                c.remove()

    res.t_start = time.time()
    with ThreadPoolExecutor(max(1, ctx.cfg.s0_parallel)) as ex:
        for f, (rec, patch) in zip(ctx.bundle.features, ex.map(one, ctx.bundle.features)):
            res.agents.append(rec)
            res.worker_patches.append((f"f{f.fid}", [f.fid], patch))
    res.t_end = time.time()
    return res


def run_s2(ctx: RunContext, spec: StrategySpec) -> StrategyResult:
    res = StrategyResult()
    feats = ctx.bundle.features
    t0 = time.time()
    # Start all containers first so the agents themselves start together.
    with ThreadPoolExecutor(len(feats)) as ex:
        boxes = list(ex.map(lambda f: _container(ctx, "S2-worker"), feats))
    res.setup_s = time.time() - t0
    try:
        res.t_start = time.time()

        def work(i):
            f, (c, base) = feats[i], boxes[i]
            prompt = prompts.single_task(f, extra=spec.extras[0] if spec.extras else None)
            rec = _agent(ctx, c, base, prompt, agent_id=f"f{f.fid}", role="worker", fids=[f.fid])
            return rec, _collect(ctx, c, base, rec)

        with ThreadPoolExecutor(len(feats)) as ex:
            outs = list(ex.map(work, range(len(feats))))
    finally:
        if not _keep():
            for c, _ in boxes:
                c.remove()
    for f, (rec, patch) in zip(feats, outs):
        res.agents.append(rec)
        res.worker_patches.append((f"f{f.fid}", [f.fid], patch))

    # ---- merge stage (same image, fresh container) ----
    merge_dir = ctx.run_dir / "merge"
    c, base = _container(ctx, "S2-merge")
    try:
        _branch_setup(c, base, res.worker_patches)
        names = [n for n, _, _ in res.worker_patches]
        pairs = pairwise_conflicts(c, base, names)
        modes = {}
        for mode in ctx.cfg.merge.modes:
            def resolver(cc, files, fids, log_dir, _mode=mode):
                involved = [f for f in feats]  # resolver sees all bundle tasks (it must keep everything working)
                rec = run_agent(
                    cc, ctx.harness, ctx.model, prompts.resolver(involved, files), _opts(ctx, False), log_dir,
                    agent_id=log_dir.name, role="resolver", feature_ids=fids, max_nudges=ctx.cfg.max_nudges,
                )
                return rec

            mres, recs = merge_mode(c, base, res.worker_patches, mode, merge_dir, resolver if mode == "llm" else None)
            res.agents += recs
            res.finals[mode] = mres.final_patch
            modes[mode] = {"lost_features": mres.lost_features, "steps": [s.__dict__ for s in mres.steps],
                           "resolver_agents": [r.agent_id for r in recs]}
        res.t_end = time.time()
        res.merge = {
            "pairwise": pairs,
            "conflict_rate": (sum(p["conflict"] for p in pairs) / len(pairs)) if pairs else 0.0,
            "overlap_lines": overlap_lines([p for _, _, p in res.worker_patches]),
            "modes": modes,
        }
    finally:
        if not _keep():
            c.remove()
    return res


def run_strategy(ctx: RunContext, spec: StrategySpec) -> StrategyResult:
    if spec.id == "S0":
        return run_s0(ctx, spec)
    if spec.id == "S1":
        return run_single_session(ctx, spec, subagents=False, default_tmpl="multi_task")
    if spec.id == "S2":
        return run_s2(ctx, spec)
    if spec.id == "S4":
        if not ctx.harness.supports_subagents:
            raise ValueError(f"S4 needs native subagents; {ctx.harness.name} has none")
        return run_single_session(ctx, spec, subagents=True, default_tmpl="harness_native")
    raise ValueError(f"unknown strategy {spec.id}")
