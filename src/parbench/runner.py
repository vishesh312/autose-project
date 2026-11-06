"""Expand an experiment config into runs, execute them, grade, and write run.json with metrics.

Run = bundle x strategy x harness x model x repeat. Results land in
results/<experiment>/<run_id>/{run.json, agents/, merge/, grading/}. Finished runs are skipped,
so an interrupted experiment can simply be re-launched.
"""

from __future__ import annotations

import json
import os
import platform
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from .config import ROOT, ExperimentConfig, Usage, load_dotenv, load_models
from .dataset import Bundle, bundles_from_subset, load_gold_conflicts, load_pools, make_bundles
from .grader import grade
from .harnesses import get_harness
from .sandbox import Container, image_exists
from .strategies import RunContext, StrategySpec, run_strategy


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")


def agent_image_name(pool_image: str, suffix: str) -> str:
    if pool_image.startswith("hostpool:"):  # no-Docker mode: there is no agent image layer
        return pool_image
    repo, _, tag = pool_image.rpartition(":")
    return f"{suffix}/{_slug(repo.split('/')[-1])}:{tag}"


def plan(cfg: ExperimentConfig) -> list[tuple[Bundle, str, str, str, int]]:
    pools = load_pools(cfg.dataset_path(), cfg.pools)
    if cfg.subset:
        sf = cfg.dataset_path() / "subsets" / f"{cfg.subset}.json"
        bundles = [b for k in cfg.k for b in bundles_from_subset(pools, sf, k, cfg.seed)]
    else:
        bundles = [b for k in cfg.k for b in make_bundles(pools, k, cfg.bundles_per_pool, cfg.seed)]
    return [(b, s, h, m, r) for b in bundles for s in cfg.strategies for h in cfg.harnesses
            for m in cfg.models for r in range(cfg.repeats)]


def run_experiment(cfg: ExperimentConfig, dry_run: bool = False) -> Path:
    load_dotenv()
    models = load_models()
    out = ROOT / cfg.results_dir / cfg.name
    out.mkdir(parents=True, exist_ok=True)
    runs = plan(cfg)
    gold = load_gold_conflicts(cfg.dataset_path())
    (out / "bundles.json").write_text(json.dumps(
        {b.id: b.to_json(gold) for b in {r[0].id: r[0] for r in runs}.values()}, indent=2))
    (out / "experiment.json").write_text(json.dumps(cfg.__dict__, default=lambda o: o.__dict__, indent=2))
    print(f"{len(runs)} runs -> {out}")
    if dry_run:
        for b, s, h, m, r in runs:
            print(f"  {s:28s} {h:12s} {m:24s} {b.id} r{r}")
        return out

    def one(args):
        b, s, h, m, r = args
        run_id = _slug(f"{s}__{h}__{m}__{b.id}__r{r}")
        run_dir = out / run_id
        if (run_dir / "run.json").exists():
            print(f"skip (done) {run_id}")
            return
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            execute_run(cfg, b, StrategySpec.parse(s), get_harness(h), models[m], r, run_dir)
            print(f"done {run_id}")
        except Exception as e:  # keep going; record the failure
            (run_dir / "error.txt").write_text(traceback.format_exc())
            print(f"FAILED {run_id}: {e}")

    with ThreadPoolExecutor(max(1, cfg.max_parallel_runs)) as ex:
        list(ex.map(one, runs))
    return out


def _env_for(cfg: ExperimentConfig, model, harness) -> dict[str, str]:
    names = set(cfg.forward_env) | set(getattr(harness, "forward_env", []))
    if model.api_key_env:
        names.add(model.api_key_env)
    return {n: os.environ[n] for n in names if os.environ.get(n)}


def _auth_files(cfg: ExperimentConfig, harness) -> list[tuple[Path, str]]:
    if not cfg.copy_auth_files:
        return []
    out = []
    for host, dest in getattr(harness, "auth_files", []):
        p = Path(os.path.expanduser(host))
        if p.exists():
            out.append((p, dest))
    return out


def execute_run(cfg, bundle: Bundle, spec: StrategySpec, harness, model, repeat: int, run_dir: Path) -> dict:
    harness.check_model(model)
    host = harness.host_mode or harness.name in cfg.host_harnesses
    # Host mode only clones the repo out of the pool image, so the pool image itself is enough (no harness layer).
    agent_image = bundle.pool.image if host else agent_image_name(bundle.pool.image, cfg.agent_image_suffix)
    if not host and not image_exists(agent_image):
        raise RuntimeError(f"agent image {agent_image} missing; run `parbench build-images` first")
    ctx = RunContext(bundle, harness, model, cfg, run_dir, agent_image, _env_for(cfg, model, harness),
                     _auth_files(cfg, harness))
    t0 = time.time()
    res = run_strategy(ctx, spec)
    t_agents_done = time.time()

    # ------------------------------------------------ grading
    gdir = run_dir / "grading"
    ckw = {"memory": cfg.container_memory, "cpus": cfg.container_cpus}
    grades: dict[str, dict[int, dict]] = {}
    feats = {f.fid: f for f in bundle.features}
    # Each agent's own patch on its own task(s): S0 score, and "passes alone" for lost-in-merge.
    for name, fids, patch in res.worker_patches:
        g = grade(bundle.pool, [feats[f] for f in fids], patch, gdir, f"own_{name}", cfg.grade_parallel, ckw)
        grades[f"own_{name}"] = {f: v.__dict__ for f, v in g.items()}
    for label, patch in res.finals.items():
        g = grade(bundle.pool, bundle.features, patch, gdir, label, cfg.grade_parallel, ckw)
        grades[label] = {f: v.__dict__ for f, v in g.items()}

    record = build_record(cfg, bundle, spec, harness, model, repeat, res, grades, t0, t_agents_done)
    (run_dir / "run.json").write_text(json.dumps(record, indent=2, default=str))
    return record


def build_record(cfg, bundle, spec, harness, model, repeat, res, grades, t0, t_agents_done) -> dict:
    agents = res.agents
    usage = sum((a.usage for a in agents), Usage())
    workers = [a for a in agents if a.role != "resolver"]
    coord = sum((a.usage for a in agents if a.role == "resolver"), Usage())
    busy = sum(a.busy_s for a in agents)
    wall = max(res.t_end - res.t_start, 1e-9)
    cost_list = model.list_cost(usage)
    cost_rep = usage.cost_reported

    # correctness
    own_pass = {}
    for name, fids, _ in res.worker_patches:
        for f in fids:
            own_pass[f] = bool(grades.get(f"own_{name}", {}).get(f, {}).get("passed"))
    finals = {}
    for label in res.finals:
        g = grades[label]
        passed = [f for f in bundle.feature_ids if g.get(f, {}).get("passed")]
        lost = [f for f in bundle.feature_ids if own_pass.get(f) and f not in passed] if spec.id == "S2" else []
        finals[label] = {
            "task_pass_rate": len(passed) / bundle.k,
            "bundle_success": len(passed) == bundle.k,
            "passed": passed,
            "lost_in_merge": lost,
        }
    if spec.id == "S0":
        passed = [f for f in bundle.feature_ids if own_pass.get(f)]
        finals["isolated"] = {"task_pass_rate": len(passed) / bundle.k, "bundle_success": len(passed) == bundle.k,
                              "passed": passed, "lost_in_merge": []}
    primary = "isolated" if spec.id == "S0" else ("final" if "final" in finals else cfg.merge.modes[-1])
    n_solved = len(finals[primary]["passed"]) if primary in finals else 0
    cost = cost_rep if cost_rep is not None else cost_list

    # repeated reading: files read by more than one worker agent
    reads = [set(a.files_read) for a in workers]
    repeated = sorted({f for a, b in combinations(reads, 2) for f in a & b}) if len(reads) > 1 else []
    wasted = Usage()
    if spec.id == "S2" and primary in finals:
        for a in workers:
            if any(f in finals[primary]["lost_in_merge"] for f in a.feature_ids):
                wasted = wasted + a.usage

    return {
        "run": {
            "experiment": cfg.name, "bundle": bundle.id, "pool": bundle.pool.id, "k": bundle.k,
            "features": bundle.feature_ids, "strategy": spec.label, "strategy_id": spec.id,
            "harness": harness.name, "model": model.id, "repeat": repeat,
            "host": platform.node(), "arch": platform.machine(), "started": t0,
        },
        "correctness": {"primary": primary, "by_final": finals, "own_pass": own_pass},
        "cost": {
            "usage": usage.to_json(),
            "cost_usd": cost,
            "cost_reported_usd": cost_rep,
            "cost_list_usd": cost_list,
            "cost_per_solved_task": (cost / n_solved) if (cost is not None and n_solved) else None,
            "coordination_tokens": coord.total,
            "coordination_overhead": coord.total / usage.total if usage.total else 0.0,
            "wasted_tokens": wasted.total,
            "repeated_reads": repeated,
        },
        "time": {
            "wall_clock_s": wall,
            "agent_busy_s": busy,
            "effective_parallelism": busy / wall,
            "container_setup_s": res.setup_s,
            "grading_s": time.time() - t_agents_done,
            "nudges": sum(a.nudges for a in agents),
            "timeouts": sum(a.timed_out for a in agents),
        },
        "merge": res.merge,
        "agents": [a.to_json() for a in agents],
        "grades": grades,
    }
