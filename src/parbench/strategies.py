"""Orchestration strategies. Strategy spec strings:  ID[@template][+extra...]

  S0   isolated: each task alone in a fresh container (k=1 reference for retention)
  S1   one agent gets all k tasks in one prompt, subagents disabled
  S2   one agent per task in parallel (own container each) -> merge (naive / union / llm resolver)
  S3   plan, then schedule (s3_planner_rules.md): a read-only planner predicts each task's files; tasks sharing a
       file run one after another in one workspace, groups run in parallel and are merged like S2.
       S3@oracle uses the gold patches' files instead of a planner (upper bound). Bad plan -> S1 fallback.
  S4   all tasks in one prompt, harness-native subagents enabled; the harness splits & integrates itself

  @template  overrides the prompt template, e.g. S4@harness_native_worktrees, S4@harness_native_encourage
  +extra     appends a prompt snippet, e.g. S2+plan_first
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .agent_runner import AgentRecord, run_agent
from .config import ExperimentConfig, ModelSpec
from .dataset import Bundle, Feature
from .grader import filter_test_files
from .harnesses.base import Harness, RunOptions
from .merge import _branch_setup, merge_mode, overlap_lines, pairwise_conflicts
from . import prompts
from .sandbox import Container, HostWorkspace
from .sandbox_policy import policy_for


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
    setup_s: float = 0.0  # container/workspace setup, summed over all containers (not part of wall-clock time)
    merge_s: float = 0.0  # S2: merging in the merge container, LLM resolver included (part of wall-clock time)
    s3: dict | None = None  # S3: plan, groups, fallback, planning quality


# ----------------------------------------------------------------- helpers
def _container(ctx: RunContext, role: str) -> tuple[Container, str]:
    want_host = (ctx.harness.host_mode or ctx.harness.name in ctx.cfg.host_harnesses
                 or ctx.agent_image.startswith("hostpool:"))  # no-Docker pools are host workspaces
    if want_host and not ctx.harness.host_capable:
        raise ValueError(f"{ctx.harness.name} has no host mode yet (host-capable: opencode, agy)")
    cls = HostWorkspace if want_host else Container
    c = cls(
        ctx.agent_image,
        env=ctx.env,
        memory=ctx.cfg.container_memory,
        cpus=ctx.cfg.container_cpus,
        labels={"parbench.role": role, "parbench.run": ctx.run_dir.name[:60]},
        sandbox=policy_for(ctx.cfg, ctx.harness, ctx.model),
    )
    try:
        c.start()
        c.scrub_history()
        for host, dest in ctx.auth_files:
            c.put_path(host, dest)
        return c, c.base_sha()
    except BaseException:
        c.remove()  # don't leak the container / host clone when setup fails
        raise


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
                                    extra=spec.extras, repo=c.repo)
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

    setup = []

    def one(f: Feature):
        t0 = time.time()
        c, base = _container(ctx, "S0")
        setup.append(time.time() - t0)
        try:
            prompt = prompts.single_task(f, extra=spec.extras, repo=c.repo)
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
    res.setup_s = sum(setup)
    return res


def run_s2(ctx: RunContext, spec: StrategySpec) -> StrategyResult:
    res = StrategyResult()
    feats = ctx.bundle.features
    t0 = time.time()
    # Start all containers first so the agents themselves start together.
    with ThreadPoolExecutor(len(feats)) as ex:
        futs = [ex.submit(_container, ctx, "S2-worker") for _ in feats]
    if any(f.exception() for f in futs):  # one failed to start: remove the ones that did
        for f in futs:
            if not f.exception():
                f.result()[0].remove()
        next(f for f in futs if f.exception()).result()
    boxes = [f.result() for f in futs]
    res.setup_s = time.time() - t0
    try:
        res.t_start = time.time()

        def work(i):
            f, (c, base) = feats[i], boxes[i]
            prompt = prompts.single_task(f, extra=spec.extras, repo=c.repo)
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

    return _merge_stage(ctx, res, res.worker_patches)


def _merge_stage(ctx: RunContext, res: StrategyResult, branches: list[tuple[str, list[int], str]]) -> StrategyResult:
    """Merge the branches' patches in a fresh workspace with every configured mode (S2 workers, S3 groups)."""
    feats = ctx.bundle.features
    merge_dir = ctx.run_dir / "merge"
    t0 = time.time()
    c, base = _container(ctx, "S2-merge")
    t_merge = time.time()
    res.setup_s += t_merge - t0
    # Merge without agent-written test files, as CooperBench does: grading drops them anyway, so a clash in a
    # test file must not count as a conflict or make naive merge skip a branch.
    patches = [(n, fids, filter_test_files(p)) for n, fids, p in branches]
    try:
        _branch_setup(c, base, patches)
        names = [n for n, _, _ in patches]
        pairs = pairwise_conflicts(c, base, names)
        modes = {}
        for mode in ctx.cfg.merge.modes:
            def resolver(cc, files, fids, log_dir, _mode=mode):
                involved = [f for f in feats]  # resolver sees all bundle tasks (it must keep everything working)
                rec = run_agent(
                    cc, ctx.harness, ctx.model, prompts.resolver(involved, files, repo=cc.repo), _opts(ctx, False), log_dir,
                    agent_id=log_dir.name, role="resolver", feature_ids=fids, max_nudges=ctx.cfg.max_nudges,
                )
                return rec

            mres, recs = merge_mode(c, base, patches, mode, merge_dir, resolver if mode == "llm" else None,
                                    exclude=ctx.harness.repo_artifacts)
            res.agents += recs
            res.finals[mode] = mres.final_patch
            modes[mode] = {"lost_features": mres.lost_features, "steps": [s.__dict__ for s in mres.steps],
                           "resolver_agents": [r.agent_id for r in recs]}
        res.t_end = time.time()
        res.merge_s = res.t_end - t_merge
        res.merge = {
            "pairwise": pairs,
            "conflict_rate": (sum(p["conflict"] for p in pairs) / len(pairs)) if pairs else 0.0,
            "overlap_lines": overlap_lines([p for _, _, p in patches]),
            "modes": modes,
        }
    finally:
        if not _keep():
            c.remove()
    return res




# ----------------------------------------------------------------- S3: plan, then schedule
def _norm_path(p: str) -> str:
    p = str(p).strip().replace("\\", "/")
    if "/repo/" in p:  # absolute workspace path -> repo-relative
        p = p.split("/repo/", 1)[1]
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def parse_plan(text: str, fids: list[int]) -> dict[int, list[str]]:
    """Planner answer -> {fid: [files]}. Raises ValueError on no/invalid JSON or unknown task ids (-> S1 fallback).
    Tasks the plan leaves out get no files (they then run in their own group)."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if not blocks:
        i, j = text.find("{"), text.rfind("}")
        blocks = [text[i:j + 1]] if 0 <= i < j else []
    plan = None
    for b in reversed(blocks):  # the final message may repeat the JSON; take the last valid one
        try:
            plan = json.loads(b)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        raise ValueError("no plan JSON with a 'tasks' list")
    out: dict[int, list[str]] = {f: [] for f in fids}
    for t in plan["tasks"]:
        m = re.search(r"\d+", str(t.get("id", "")))
        fid = int(m.group()) if m else None
        if fid not in out:
            raise ValueError(f"unknown task id {t.get('id')!r}")
        files = [_norm_path(f["path"] if isinstance(f, dict) else f) for f in t.get("files", []) or []]
        out[fid] = sorted({f for f in files if f})
    return out


def s3_groups(files: dict[int, list[str]], order: list[int]) -> list[list[int]]:
    """Connected components of 'shares a file', each in the bundle's seeded order; groups ordered by first task."""
    parent = {f: f for f in order}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(order):
        for b in order[i + 1:]:
            if set(files.get(a, [])) & set(files.get(b, [])):
                parent[root(b)] = root(a)
    groups: dict[int, list[int]] = {}
    for f in order:
        groups.setdefault(root(f), []).append(f)
    return list(groups.values())


def planning_quality(pred: dict[int, list[str]], gold: dict[int, list[str]],
                     gold_conflicts: set[tuple[int, int]]) -> dict:
    """File recall/precision (micro over tasks) and clash prediction over task pairs (docs/research/Task4_Metrics.md).
    Clash truth is given two ways: gold patches that conflict under git merge, and gold patches sharing a file."""
    hit = sum(len(set(pred[f]) & set(gold.get(f, []))) for f in pred)
    n_gold = sum(len(gold.get(f, [])) for f in pred)
    n_pred = sum(len(pred[f]) for f in pred)
    fids = sorted(pred)
    pairs = [(a, b) for i, a in enumerate(fids) for b in fids[i + 1:]]
    p_clash = {p for p in pairs if set(pred[p[0]]) & set(pred[p[1]])}
    share = {p for p in pairs if set(gold.get(p[0], [])) & set(gold.get(p[1], []))}

    def pr(truth):
        tp = len(p_clash & truth)
        return {"precision": tp / len(p_clash) if p_clash else None, "recall": tp / len(truth) if truth else None,
                "true": sorted(truth), "predicted": sorted(p_clash)}

    return {"file_recall": hit / n_gold if n_gold else None, "file_precision": hit / n_pred if n_pred else None,
            "clash_vs_git_conflict": pr({p for p in pairs if p in gold_conflicts}),
            "clash_vs_shared_gold_file": pr(share)}


def _plan_text(ctx: RunContext, rec: AgentRecord) -> str:
    """The planner's last message, read in full from its logs (AgentRecord keeps only a 1500-char tail)."""
    log_dir = ctx.run_dir / "agents" / rec.agent_id
    text = ""
    for f in sorted(log_dir.glob("attempt*.stdout.jsonl"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        t = ctx.harness.parse(f.read_text(errors="replace"), "").final_text
        text = t or text
    return text


def _plan_problem(text: str, fids: list[int]) -> str | None:
    """Nudge reason if the planner's final message has no usable plan, else None."""
    try:
        parse_plan(text, fids)
        return None
    except ValueError as e:
        return f"your last message did not contain the plan JSON ({e})"


def run_s3(ctx: RunContext, spec: StrategySpec) -> StrategyResult:
    from .dataset import load_gold_conflicts

    feats = {f.fid: f for f in ctx.bundle.features}
    order = ctx.bundle.feature_ids
    gold = {f.fid: f.gold_files() for f in ctx.bundle.features}
    gc = {(min(a, b), max(a, b)) for (pool, a, b) in load_gold_conflicts(ctx.cfg.dataset_path())
          if pool == ctx.bundle.pool.id}
    info: dict = {"oracle": spec.template == "oracle", "fallback": False}
    planner_recs: list[AgentRecord] = []
    t_plan = time.time()
    if info["oracle"]:
        files = gold
    else:
        c, base = _container(ctx, "S3-planner")
        try:
            opts = RunOptions(subagents=False, max_turns=ctx.cfg.max_turns, timeout_s=ctx.cfg.agent_timeout_s,
                              read_only=True)
            # base_sha=None: the planner must not edit, so no "no_changes" nudge (that nudge says "keep implementing",
            # which made v1 planners write code instead of a plan). One extra nudge asks for the JSON if it is missing.
            rec = run_agent(c, ctx.harness, ctx.model, prompts.planner(ctx.bundle.features, repo=c.repo), opts,
                            ctx.run_dir / "agents" / "planner", agent_id="planner", role="planner",
                            feature_ids=order, max_nudges=ctx.cfg.max_nudges + 1, base_sha=None,
                            check_final=lambda text: _plan_problem(text, order), nudge_template="nudge_planner")
            planner_recs.append(rec)
            info["planner_read_only"] = ctx.harness.supports_read_only
            info["planner_version"], info["planner_nudges"] = 2, rec.nudges
            info["planner_edited"] = bool(c.diff_against(base, exclude=ctx.harness.repo_artifacts).strip())
        finally:
            if not _keep():
                c.remove()
        raw = _plan_text(ctx, rec)
        (ctx.run_dir / "agents" / "planner").mkdir(parents=True, exist_ok=True)
        (ctx.run_dir / "agents" / "planner" / "plan_raw.txt").write_text(raw)
        try:
            files = parse_plan(raw, order)
        except ValueError as e:
            info.update(fallback=True, fallback_reason=str(e))
            files = None
    info["plan_s"] = time.time() - t_plan

    if files is None:  # rule 5: fall back to S1 (everything sequential), reported separately via s3.fallback
        res = run_single_session(ctx, StrategySpec("S1", None, spec.extras), subagents=False, default_tmpl="multi_task")
        res.agents[:0] = planner_recs
        res.t_start = t_plan
        res.s3 = info
        return res

    groups = s3_groups(files, order)
    info.update(plan={f"f{f}": files[f] for f in order}, gold_files={f"f{f}": gold[f] for f in order},
                groups=[[f"f{f}" for f in g] for g in groups])
    if not info["oracle"]:
        info["planning"] = planning_quality(files, gold, gc)

    res = StrategyResult(s3=info)
    res.agents += planner_recs
    t0 = time.time()
    with ThreadPoolExecutor(len(groups)) as ex:
        futs = [ex.submit(_container, ctx, "S3-group") for _ in groups]
    if any(f.exception() for f in futs):
        for f in futs:
            if not f.exception():
                f.result()[0].remove()
        next(f for f in futs if f.exception()).result()
    boxes = [f.result() for f in futs]
    res.setup_s = time.time() - t0
    res.t_start = t_plan  # planning is part of S3's time

    def chain(i):
        """One group: a fresh agent per task, one after another, each starting from the tree the last one left."""
        (c, base), recs, per_task = boxes[i], [], []
        for fid in groups[i]:
            prompt = prompts.single_task(feats[fid], extra=spec.extras, repo=c.repo)
            rec = _agent(ctx, c, base, prompt, agent_id=f"f{fid}", role="worker", fids=[fid])
            patch = _collect(ctx, c, base, rec)  # cumulative: this group's changes so far
            recs.append(rec)
            per_task.append((f"f{fid}", [fid], patch))
        return recs, per_task

    try:
        with ThreadPoolExecutor(len(groups)) as ex:
            outs = list(ex.map(chain, range(len(groups))))
    finally:
        if not _keep():
            for c, _ in boxes:
                c.remove()
    branches = []
    for g, (recs, per_task) in zip(groups, outs):
        res.agents += recs
        res.worker_patches += per_task  # own grading: does the task pass right after its agent?
        branches.append(("g" + "-".join(str(f) for f in g), g, per_task[-1][2]))
    if len(branches) == 1:  # one group: nothing to merge
        res.t_end = time.time()
        res.finals["final"] = branches[0][2]
        return res
    return _merge_stage(ctx, res, branches)


def run_strategy(ctx: RunContext, spec: StrategySpec) -> StrategyResult:
    if spec.id == "S0":
        return run_s0(ctx, spec)
    if spec.id == "S1":
        return run_single_session(ctx, spec, subagents=False, default_tmpl="multi_task")
    if spec.id == "S2":
        return run_s2(ctx, spec)
    if spec.id == "S3":
        return run_s3(ctx, spec)
    if spec.id == "S4":
        if not ctx.harness.supports_subagents:
            raise ValueError(f"S4 needs native subagents; {ctx.harness.name} has none")
        return run_single_session(ctx, spec, subagents=True, default_tmpl="harness_native")
    raise ValueError(f"unknown strategy {spec.id}")
