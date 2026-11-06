"""parbench CLI. Run `parbench <cmd> -h` for options."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from .config import ROOT, ExperimentConfig, load_dotenv, load_models

DEFAULT_DATASET = ROOT / "external" / "CooperBench" / "dataset"
TOY_DATASET = ROOT / "smoke" / "dataset"


def _pools(args):
    from .dataset import load_pools

    root = TOY_DATASET if getattr(args, "toy", False) else Path(args.dataset)
    return load_pools(root, args.pools or None)


def cmd_list_pools(args):
    for pid, p in _pools(args).items():
        print(f"{pid:45s} n={len(p.features):2d}  {p.image}")


def cmd_bundles(args):
    from .dataset import load_gold_conflicts, make_bundles

    pools = _pools(args)
    gold = load_gold_conflicts(Path(args.dataset))
    bundles = make_bundles(pools, args.k, args.per_pool, args.seed)
    print(json.dumps([b.to_json(gold) for b in bundles], indent=2))


def cmd_build_images(args):
    from .runner import agent_image_name
    from .sandbox import ensure_image

    for pid, p in _pools(args).items():
        if not (p.dir / "IMAGE").exists():
            ensure_image(p.image)
        tag = agent_image_name(p.image, args.suffix)
        print(f"== {pid}: {p.image} -> {tag}")
        cmd = ["docker", "build", "-f", str(ROOT / "docker" / "agent.Dockerfile"),
               "--build-arg", f"BASE={p.image}", "--build-arg", f"HARNESSES={' '.join(args.harnesses)}",
               "-t", tag, str(ROOT / "docker")]
        subprocess.run(cmd, check=True)


def cmd_build_toy(args):
    for pool_dir in sorted(TOY_DATASET.glob("*/task*")):
        tag = (pool_dir / "IMAGE").read_text().strip()
        print(f"== building toy pool image {tag}")
        subprocess.run(["docker", "build", "-t", tag, str(pool_dir)], check=True)


def cmd_check_gold(args):
    """Sanity-check the grader: tests alone fail, gold feature patch passes, combined.patch passes all."""
    from .grader import grade

    out = ROOT / "results" / "_gold_checks"
    for pid, p in _pools(args).items():
        feats = list(p.features.values())
        if args.features:
            feats = [f for f in feats if f.fid in args.features]
        d = out / pid.replace("/", "__")
        rows = []
        base = grade(p, feats, "", d, "no_patch", args.parallel)
        for f in feats:
            g = grade(p, [f], f.feature_patch.read_text(), d, f"gold_f{f.fid}", 1)
            rows.append((f.fid, base[f.fid].passed, g[f.fid].passed))
        comb = grade(p, feats, p.combined_patch.read_text(), d, "combined", args.parallel) if p.combined_patch else {}
        print(f"== {pid}")
        print("  fid  tests-alone-pass(should be False)  gold-pass  combined-pass")
        for fid, b, g in rows:
            print(f"  {fid:3d}  {str(b):34s} {str(g):10s} {comb.get(fid).passed if fid in comb else '-'}")


def cmd_run(args):
    from .runner import run_experiment

    cfg = ExperimentConfig.load(Path(args.config))
    run_experiment(cfg, dry_run=args.dry_run)


def cmd_report(args):
    from .report import report

    print(report(Path(args.exp_dir)))


def cmd_probe(args):
    """One agent, one prompt, in a pool's agent image. Prints the parsed usage + diff. For adapter debugging."""
    from .agent_runner import run_agent
    from .dataset import load_pools
    from .harnesses import get_harness
    from .harnesses.base import RunOptions
    from .prompts import render
    from .runner import _auth_files, _env_for, agent_image_name
    from .sandbox import Container

    load_dotenv()
    models = load_models()
    model, h = models[args.model], get_harness(args.harness)
    h.check_model(model)
    root = TOY_DATASET if args.toy else Path(args.dataset)
    pool = next(iter(load_pools(root, [args.pool] if args.pool else None).values()))
    cfg = ExperimentConfig(name="probe", copy_auth_files=args.copy_auth)
    prompt = Path(args.prompt_file).read_text() if args.prompt_file else args.prompt
    prompt = render("single_task", task=prompt)
    log_dir = ROOT / "results" / "_probes" / f"{args.harness}__{args.model.replace('/', '_')}__{int(time.time())}"
    with Container(agent_image_name(pool.image, args.suffix), env=_env_for(cfg, model, h)) as c:
        c.scrub_history()
        for host, dest in _auth_files(cfg, h):
            c.put_path(host, dest)
        base = c.base_sha()
        rec = run_agent(c, h, model, prompt, RunOptions(subagents=args.subagents, max_turns=args.max_turns,
                        timeout_s=args.timeout), log_dir, agent_id="probe", role="probe", feature_ids=[],
                        max_nudges=args.max_nudges, base_sha=base)
        diff = c.diff_against(base, exclude=h.repo_artifacts)
    (log_dir / "patch.diff").write_text(diff)
    print(json.dumps({k: rec.to_json()[k] for k in ("usage", "cost_list", "busy_s", "nudges", "timed_out",
                      "returncode", "tool_calls", "files_read", "files_edited", "error")}, indent=2))
    print(f"--- diff ({len(diff.splitlines())} lines) ---\n{diff[:3000]}")
    print(f"logs: {log_dir}")


def cmd_cleanup(args):
    from .sandbox import cleanup_all

    cleanup_all()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="parbench")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def pool_args(p):
        p.add_argument("--dataset", default=str(DEFAULT_DATASET))
        p.add_argument("--pools", nargs="*", help="pool ids (repo/taskN) or repo names")
        p.add_argument("--toy", action="store_true", help="use the toy smoke-test dataset")

    p = sub.add_parser("list-pools"); pool_args(p); p.set_defaults(f=cmd_list_pools)
    p = sub.add_parser("bundles"); pool_args(p)
    p.add_argument("--k", type=int, default=3); p.add_argument("--per-pool", type=int, default=None)
    p.add_argument("--seed", type=int, default=0); p.set_defaults(f=cmd_bundles)

    p = sub.add_parser("build-images", help="build agent images (pool image + harness CLIs)"); pool_args(p)
    p.add_argument("--harnesses", nargs="*", default=["opencode", "pi", "claude", "codex", "gemini", "agy"])
    p.add_argument("--suffix", default="parbench-agent"); p.set_defaults(f=cmd_build_images)
    p = sub.add_parser("build-toy", help="build the toy pool base images"); p.set_defaults(f=cmd_build_toy)

    p = sub.add_parser("check-gold", help="validate grading on gold patches"); pool_args(p)
    p.add_argument("--features", nargs="*", type=int); p.add_argument("--parallel", type=int, default=2)
    p.set_defaults(f=cmd_check_gold)

    p = sub.add_parser("run"); p.add_argument("config"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(f=cmd_run)
    p = sub.add_parser("report"); p.add_argument("exp_dir"); p.set_defaults(f=cmd_report)

    p = sub.add_parser("probe", help="run one agent on one prompt (adapter debugging)"); pool_args(p)
    p.add_argument("--harness", required=True); p.add_argument("--model", required=True)
    p.add_argument("--pool"); p.add_argument("--prompt", default="Add a one-line docstring to the main module.")
    p.add_argument("--prompt-file"); p.add_argument("--subagents", action="store_true")
    p.add_argument("--max-turns", type=int, default=30); p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--max-nudges", type=int, default=1); p.add_argument("--copy-auth", action="store_true")
    p.add_argument("--suffix", default="parbench-agent"); p.set_defaults(f=cmd_probe)

    p = sub.add_parser("cleanup", help="remove all parbench containers"); p.set_defaults(f=cmd_cleanup)

    args = ap.parse_args(argv)
    args.f(args)


if __name__ == "__main__":
    sys.exit(main())
