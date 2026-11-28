"""Aggregate run.json files into a flat CSV + a markdown summary per (strategy, harness, model, k)."""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def flatten(rec: dict) -> dict:
    r, c, cost, t = rec["run"], rec["correctness"], rec["cost"], rec["time"]
    prim = c["by_final"].get(c["primary"], {})
    u = cost["usage"]  # proxy (server-side) counts when token_source == "proxy"; older runs: harness-reported
    h = cost.get("usage_harness") or u
    row = {
        "strategy": r["strategy"], "harness": r["harness"], "model": r["model"], "k": r["k"],
        "bundle": r["bundle"], "repeat": r["repeat"], "sandbox": (r.get("sandbox") or {}).get("mode", ""),
        "task_pass_rate": prim.get("task_pass_rate"), "bundle_success": int(bool(prim.get("bundle_success"))),
        "lost_in_merge": len(prim.get("lost_in_merge", [])),
        "tokens_in": u["input"], "tokens_cached": u["cached_input"], "tokens_out": u["output"],
        "tokens_reasoning": u["reasoning"], "tokens_total": u["input"] + u["output"],
        "token_source": cost.get("token_source", "harness"), "tokens_total_harness": h["input"] + h["output"],
        "cost_usd": cost["cost_usd"],
        "cost_per_solved": cost["cost_per_solved_task"], "coord_overhead": cost["coordination_overhead"],
        "wasted_tokens": cost["wasted_tokens"], "repeated_reads": len(cost["repeated_reads"]),
        "wall_s": t["wall_clock_s"], "busy_s": t["agent_busy_s"], "parallelism": t["effective_parallelism"],
        "nudges": t["nudges"], "timeouts": t["timeouts"],
    }
    s3 = rec.get("s3")
    if s3:
        pq = s3.get("planning") or {}
        row.update(s3_fallback=int(bool(s3.get("fallback"))), s3_groups=len(s3.get("groups") or []),
                   plan_file_recall=pq.get("file_recall"), plan_file_precision=pq.get("file_precision"),
                   s3_executed=int(s3.get("executed", True)), planner_nudges=s3.get("planner_nudges"),
                   plan_clash_found=(pq.get("clash_vs_shared_gold_file") or {}).get("recall"))
    m = rec.get("merge")
    if m:
        row["conflict_rate"] = m["conflict_rate"]
        row["overlap_lines"] = m["overlap_lines"]
        for mode, v in c["by_final"].items():
            row[f"pass_{mode}"] = v["task_pass_rate"]
    return row


def wilson(p_hat: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    d = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / d
    half = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / d
    return (max(0, centre - half), min(1, centre + half))


def report(exp_dir: Path) -> str:
    rows, invalid = [], []
    for p in sorted(exp_dir.glob("*/run.json")):
        rec = json.loads(p.read_text())
        if rec.get("valid", True):
            rows.append(flatten(rec))
        else:
            invalid.append(p.parent.name)
    failed = sorted(p.parent.name for p in exp_dir.glob("*/error.txt") if not (p.parent / "run.json").exists())
    if not rows:
        return f"no finished runs in {exp_dir} ({len(failed)} failed)"
    keys = sorted({k for r in rows for k in r})
    with open(exp_dir / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    # S0 pass rate per (harness, model, bundle) for retention
    s0 = defaultdict(list)
    for r in rows:
        if r["strategy"].startswith("S0"):
            s0[(r["harness"], r["model"], r["bundle"])].append(r["task_pass_rate"])

    groups = defaultdict(list)
    for r in rows:
        if r["task_pass_rate"] is None:  # S3@planonly with nothing executed: only in the planning table below
            continue
        groups[(r["strategy"], r["harness"], r["model"], r["k"])].append(r)
    lines = [
        "| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (s, h, m, k), rs in sorted(groups.items()):
        n = len(rs)
        tasks_n = n * k
        tpr = statistics.mean(r["task_pass_rate"] for r in rs)
        lo, hi = wilson(tpr, tasks_n)
        bs = statistics.mean(r["bundle_success"] for r in rs)
        base = [statistics.mean(s0[(h, m, r["bundle"])]) for r in rs if s0.get((h, m, r["bundle"]))]
        ret = (tpr / statistics.mean(base)) if base and statistics.mean(base) > 0 else None
        conf = [r["conflict_rate"] for r in rs if "conflict_rate" in r]
        cps = [r["cost_per_solved"] for r in rs if r["cost_per_solved"] is not None]
        lines.append(
            f"| {s} | {h} | {m} | {k} | {n} | {tpr:.2f} ({lo:.2f}-{hi:.2f}) | {bs:.2f} | "
            f"{'' if ret is None else f'{ret:.2f}'} | {'' if not conf else f'{statistics.mean(conf):.2f}'} | "
            f"{'' if not cps else f'{statistics.median(cps):.3f}'} | "
            f"{statistics.median(r['tokens_in'] + r['tokens_out'] for r in rs):,.0f} | "
            f"{statistics.median(r['wall_s'] for r in rs):.0f} | "
            f"{statistics.median(r['parallelism'] for r in rs):.2f} | {sum(r['nudges'] for r in rs)} |"
        )
    md = "\n".join(lines)
    plans = defaultdict(list)
    for r in rows:
        if "s3_fallback" in r and not r["strategy"].startswith("S3@oracle"):
            plans[(r["strategy"], r["model"])].append(r)
    if plans:
        md += ("\n\nS3 planning (planner runs; recall/precision of predicted vs gold files; clash found = the planner"
               " saw that tasks share a file):\n\n| strategy | model | n | valid plan | JSON nudge needed | file recall |"
               " file precision | clash found | split plans (>1 group) | executed |\n|---|---|---|---|---|---|---|---|---|---|")
        avg = lambda xs: f"{statistics.mean(xs):.2f}" if xs else ""
        for (s, m), rs in sorted(plans.items()):
            ok = [r for r in rs if not r["s3_fallback"]]
            md += (f"\n| {s} | {m} | {len(rs)} | {len(ok)}/{len(rs)} | {sum(1 for r in rs if r.get('planner_nudges'))} | "
                   f"{avg([r['plan_file_recall'] for r in ok if r.get('plan_file_recall') is not None])} | "
                   f"{avg([r['plan_file_precision'] for r in ok if r.get('plan_file_precision') is not None])} | "
                   f"{avg([r['plan_clash_found'] for r in ok if r.get('plan_clash_found') is not None])} | "
                   f"{sum(1 for r in ok if r['s3_groups'] > 1)} | {sum(r.get('s3_executed', 1) for r in rs)} |")
    src = defaultdict(int)
    for r in rows:
        src[r["token_source"]] += 1
    md += "\n\nToken source (docs/metrics_tokens.md): " + ", ".join(f"{k} {v} runs" for k, v in sorted(src.items()))
    if invalid:
        md += f"\n\n{len(invalid)} runs excluded as invalid (an agent ended on a quota/capacity error): " + ", ".join(invalid[:12])
    if failed:
        md += f"\n\n{len(failed)} failed runs (see error.txt): " + ", ".join(failed[:10])
    (exp_dir / "summary.md").write_text(md + "\n")
    return md


WEB_TOOLS = ("search_web", "read_url_content", "browser", "fetch", "web_search", "webfetch")
_LEAK = ("github.com", "/pull/", "/issues/", "pull request", " pr ", "upstream", "commit")


def audit_web(exp_dir: Path) -> str:
    """Which agents used web tools (agy logs), and which queries look like a hunt for the upstream fix.

    Web access can leak the real implementation of a CooperBench task (they come from public PRs), so runs
    with web calls are flagged as possibly contaminated. Reads the raw logs, so it works for finished and
    unfinished runs.
    """
    import glob
    import json

    rows = []
    for run in sorted(glob.glob(str(exp_dir / "*/"))):
        calls, leaky = 0, []
        for f in glob.glob(run.rstrip("/") + "/agents/*/attempt*.stdout.jsonl"):
            for line in open(f, errors="replace"):
                if not line.startswith("{"):
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                su = e.get("step_update") or {}
                name = su.get("tool_name") or ""
                if e.get("event") == "step_update" and su.get("state") == "ACTIVE" and any(w in name for w in WEB_TOOLS):
                    calls += 1
                    q = json.dumps((su.get("tool_info") or {}).get("parameters", {}))
                    if any(k in q.lower() for k in _LEAK):
                        leaky.append(q[:110])
        if calls:
            rows.append((Path(run).name, calls, leaky))
    out = ["| run | web calls | queries that look like looking up the upstream change |", "|---|---|---|"]
    for name, calls, leaky in rows:
        out.append(f"| {name} | {calls} | {len(leaky)}{(': ' + leaky[0]) if leaky else ''} |")
    return "\n".join(out) if rows else "no web tool use found"


def _leak_re():
    import re

    from .config import ROOT

    return re.compile("|".join([r"CooperBench", r"/dataset/", r"feature\.patch", r"tests\.patch", r"combined\.patch",
                                r"_gold_checks", r"\bresults/", re.escape(str(ROOT))]), re.I)


_NET = (r"\b(?:curl|wget|aria2c|nc|ncat|telnet)\s|\bpip3?\s+(?:download|install)\b|\buv\s+(?:pip\s+install|add|sync)\b"
        r"|\bgit\s+(?:clone|fetch|pull|ls-remote)\b|\bnpm\s+(?:i|install)\b|https?://(?!localhost|127\.0\.0\.1)")


def scan_calls(calls: list[dict]) -> tuple[list[str], list[str]]:
    """(calls touching the dataset / gold / hidden tests / parbench checkout, network attempts incl. shell curl)."""
    import re

    leak_re, net_re = _leak_re(), re.compile(_NET, re.I)
    leaks, net = [], []
    for c in calls:
        text = json.dumps(c.get("args", {}))
        if leak_re.search(text):
            leaks.append(f"{c.get('name')}: {text[:120]}")
        if c.get("kind") == "web" or net_re.search(text):
            net.append(f"{c.get('name')}: {text[:120]}")
    return leaks, net


def audit_leak(exp_dir: Path) -> str:
    """Runs whose agents touched the dataset (gold feature.patch, hidden tests.patch) or the parbench checkout, or
    tried the network (web tools, shell curl/wget/pip/git clone). Reads agents/*/tool_calls.jsonl; for agents that
    did not finish, the raw attempt logs are searched as text (may over-report). `agy` cannot be stopped from
    reading files outside its workspace, so run this on every agy experiment."""
    rows = []
    for run in sorted(p for p in exp_dir.iterdir() if p.is_dir()):
        leaks, net = [], []
        for agent in sorted((run / "agents").glob("*")):
            tc = agent / "tool_calls.jsonl"
            if tc.exists():
                calls = [json.loads(line) for line in tc.read_text(errors="replace").splitlines() if line.strip()]
            else:  # unfinished agent: treat every raw log line as one call's arguments
                calls = [{"name": f"{agent.name}/raw", "args": {"line": line[:2000]}}
                         for f in sorted(agent.glob("attempt*.stdout.jsonl"))
                         for line in f.read_text(errors="replace").splitlines()]
            lk, nt = scan_calls(calls)
            leaks += [f"{agent.name} {x}" for x in lk]
            net += [f"{agent.name} {x}" for x in nt]
        if leaks or net:
            rows.append((run.name, leaks, net))
    out = ["| run | dataset/gold access | network attempts | first example |", "|---|---|---|---|"]
    for name, leaks, net in rows:
        out.append(f"| {name} | {len(leaks)} | {len(net)} | {(leaks or net)[0].replace('|', '/')} |")
    return "\n".join(out) if rows else "no dataset access or network attempts found"
