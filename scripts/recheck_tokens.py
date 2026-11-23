#!/usr/bin/env python3
"""Re-parse the raw agent logs of finished runs with the current parsers and compare with the token counts
stored in run.json. Read-only: prints a table, never rewrites results.

    PYTHONPATH=src python scripts/recheck_tokens.py results/core_agy [more dirs...]

Why: before 2026-11-23 the agy parser took `result.usage` per attempt, but that is a running total for the
whole conversation, so every resumed attempt (nudge or infra retry) re-counted all earlier ones
(docs/metrics_tokens.md). Only attempts listed in each agent's record.json are used (stale logs are ignored).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from parbench.config import Usage
from parbench.harnesses import get_harness


def recheck_agent(agent_dir: Path, rec: dict) -> Usage:
    h = get_harness(rec["harness"])
    total, prev = Usage(), Usage()
    for a in rec["attempts"]:
        f = agent_dir / f"attempt{a['index']}.stdout.jsonl"
        err = agent_dir / f"attempt{a['index']}.stderr.log"
        p = h.parse(f.read_text() if f.exists() else "", err.read_text() if err.exists() else "")
        d = p.usage
        if h.usage_is_cumulative:
            d, prev = p.usage - prev, p.usage
        total = total + d
    return total


def main(dirs: list[str]) -> None:
    by = defaultdict(lambda: [Usage(), Usage(), 0, 0])  # key -> [old, new, runs, runs changed]
    print("run | old total | new total | old input | new input | error")
    for d in dirs:
        for rj in sorted(Path(d).glob("*/run.json")):
            run = json.loads(rj.read_text())
            if not run.get("valid", True):
                continue
            old, new = Usage(), Usage()
            for ag in run["agents"]:
                adir = rj.parent / "agents" / ag["agent_id"]
                if ag["role"] == "resolver":
                    adir = next(iter(rj.parent.glob(f"merge/*/{ag['agent_id']}")), adir)
                if not (adir / "record.json").exists():
                    adir = next((p.parent for p in rj.parent.rglob("record.json")
                                 if json.loads(p.read_text())["agent_id"] == ag["agent_id"]), adir)
                old = old + Usage(**{k: v for k, v in ag["usage"].items() if k in Usage.__dataclass_fields__})
                new = new + recheck_agent(adir, ag)
            r = run["run"]
            key = (Path(d).name, r["harness"], r["model"], r["strategy"])
            b = by[key]
            b[0], b[1], b[2] = b[0] + old, b[1] + new, b[2] + 1
            b[3] += old.total != new.total
            err = (old.total - new.total) / new.total if new.total else 0.0
            print(f"{rj.parent.name} | {old.total:,} | {new.total:,} | {old.input:,} | {new.input:,} | {err:+.1%}")
    print("\nexperiment | harness | model | strategy | runs | runs changed | old total | new total | overcount")
    allo, alln = Usage(), Usage()
    for (e, h, m, s), (o, n, k, ch) in sorted(by.items()):
        allo, alln = allo + o, alln + n
        print(f"{e} | {h} | {m} | {s} | {k} | {ch} | {o.total:,} | {n.total:,} | "
              f"{(o.total - n.total) / n.total if n.total else 0:+.1%}")
    if alln.total:
        print(f"ALL | | | | | | {allo.total:,} | {alln.total:,} | {(allo.total - alln.total) / alln.total:+.1%}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["results/core_agy"])
