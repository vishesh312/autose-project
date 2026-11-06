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
    u = cost["usage"]
    row = {
        "strategy": r["strategy"], "harness": r["harness"], "model": r["model"], "k": r["k"],
        "bundle": r["bundle"], "repeat": r["repeat"],
        "task_pass_rate": prim.get("task_pass_rate"), "bundle_success": int(bool(prim.get("bundle_success"))),
        "lost_in_merge": len(prim.get("lost_in_merge", [])),
        "tokens_in": u["input"], "tokens_cached": u["cached_input"], "tokens_out": u["output"],
        "tokens_reasoning": u["reasoning"], "cost_usd": cost["cost_usd"],
        "cost_per_solved": cost["cost_per_solved_task"], "coord_overhead": cost["coordination_overhead"],
        "wasted_tokens": cost["wasted_tokens"], "repeated_reads": len(cost["repeated_reads"]),
        "wall_s": t["wall_clock_s"], "busy_s": t["agent_busy_s"], "parallelism": t["effective_parallelism"],
        "nudges": t["nudges"], "timeouts": t["timeouts"],
    }
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
    rows = []
    for p in sorted(exp_dir.glob("*/run.json")):
        rows.append(flatten(json.loads(p.read_text())))
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
