"""Load CooperBench-layout datasets: pools (CooperBench "tasks") made of features (our "tasks").

Layout (same for CooperBench and our toy pools):
    <root>/<repo>/task<id>/Dockerfile, runner.sh, combined.patch
    <root>/<repo>/task<id>/feature<N>/feature.md, feature.patch, tests.patch
An optional <pool>/IMAGE file overrides the Docker image name (used by toy pools).
"""

from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

COOPERBENCH_REGISTRY = "akhatua/cooperbench"


@dataclass
class Feature:
    pool_id: str
    fid: int
    dir: Path

    @property
    def description(self) -> str:
        return (self.dir / "feature.md").read_text()

    @property
    def feature_patch(self) -> Path:
        return self.dir / "feature.patch"

    @property
    def tests_patch(self) -> Path:
        return self.dir / "tests.patch"

    @property
    def key(self) -> str:
        return f"{self.pool_id}/f{self.fid}"

    def gold_files(self) -> list[str]:
        """Non-test files touched by the gold patch (ground truth for planner file recall)."""
        if not self.feature_patch.exists():
            return []
        files = re.findall(r"^diff --git a/(\S+) b/", self.feature_patch.read_text(), re.M)
        return sorted(set(files))


@dataclass
class Pool:
    repo: str
    task_id: str
    dir: Path
    features: dict[int, Feature] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.repo}/task{self.task_id}"

    @property
    def image(self) -> str:
        if os.environ.get("PARBENCH_HOST_POOLS"):  # no-Docker mode: pool = a prepared host directory
            return f"hostpool:{self.repo}/task{self.task_id}"
        override = self.dir / "IMAGE"
        if override.exists():
            return override.read_text().strip()
        repo_clean = self.repo.replace("_task", "").replace("_", "-")
        return f"{COOPERBENCH_REGISTRY}-{repo_clean}:task{self.task_id}"

    @property
    def combined_patch(self) -> Path | None:
        p = self.dir / "combined.patch"
        return p if p.exists() else None


def load_pools(root: Path, only: list[str] | None = None) -> dict[str, Pool]:
    """Discover all pools under a dataset root. `only` filters by pool id, e.g. 'pallets_jinja_task/task1621'."""
    pools: dict[str, Pool] = {}
    for pool_dir in sorted(root.glob("*/task*")):
        if not pool_dir.is_dir():
            continue
        repo, task_id = pool_dir.parent.name, pool_dir.name.removeprefix("task")
        pool = Pool(repo=repo, task_id=task_id, dir=pool_dir)
        for fdir in sorted(pool_dir.glob("feature*")):
            m = re.fullmatch(r"feature(\d+)", fdir.name)
            if m and (fdir / "feature.md").exists():
                fid = int(m.group(1))
                pool.features[fid] = Feature(pool_id=pool.id, fid=fid, dir=fdir)
        if not pool.features:
            continue
        if only and pool.id not in only and repo not in only:
            continue
        pools[pool.id] = pool
    return pools


def load_gold_conflicts(root: Path) -> set[tuple[str, int, int]]:
    """Pairs of gold patches that conflict under plain `git merge` (CooperBench's report)."""
    report = root / "gold_conflict_report.json"
    if not report.exists():
        return set()
    data = json.loads(report.read_text())
    out = set()
    for r in data.get("all_results", []):
        if r.get("has_conflict"):
            a, b = sorted((r["f1"], r["f2"]))
            out.add((f"{r['repo']}/task{r['task_id']}", a, b))
    return out


@dataclass
class Bundle:
    """k features from one pool, in a fixed (seeded) order used for S1 prompts and S2 merge order."""

    pool: Pool
    feature_ids: list[int]

    @property
    def k(self) -> int:
        return len(self.feature_ids)

    @property
    def id(self) -> str:
        return f"{self.pool.id}/k{self.k}/" + "-".join(f"f{f}" for f in self.feature_ids)

    @property
    def features(self) -> list[Feature]:
        return [self.pool.features[f] for f in self.feature_ids]

    def to_json(self, gold_conflicts: set | None = None) -> dict:
        d = {
            "id": self.id,
            "pool": self.pool.id,
            "image": self.pool.image,
            "k": self.k,
            "features": self.feature_ids,
            "gold_files": {f.fid: f.gold_files() for f in self.features},
        }
        if gold_conflicts is not None:
            d["gold_conflict_pairs"] = [
                [a, b]
                for a, b in combinations(sorted(self.feature_ids), 2)
                if (self.pool.id, a, b) in gold_conflicts
            ]
        return d


def make_bundles(pools: dict[str, Pool], k: int, per_pool: int | None, seed: int) -> list[Bundle]:
    """Sample up to `per_pool` k-subsets per pool (all if None). Order inside a bundle is shuffled by seed."""
    import random

    rng = random.Random(f"{seed}-{k}")
    bundles = []
    for pool in pools.values():
        ids = sorted(pool.features)
        if len(ids) < k:
            continue
        combos = [list(c) for c in combinations(ids, k)]
        if per_pool is not None and len(combos) > per_pool:
            combos = rng.sample(combos, per_pool)
        for c in combos:
            rng.shuffle(c)
            bundles.append(Bundle(pool=pool, feature_ids=c))
    return bundles


def bundles_from_subset(pools: dict[str, Pool], subset_file: Path, k: int, seed: int) -> list[Bundle]:
    """Use the pairs of a CooperBench subset (core, flash_10, flash, lite, ...) as the base of each bundle.

    k=2 gives the pairs as listed. k>2 extends each pair with k-2 more features of the same pool, chosen with a
    seeded RNG (pairs whose pool has too few features are skipped), so every k-bundle contains a curated pair.
    """
    import random

    rng = random.Random(f"{seed}-{k}-subset")
    data = json.loads(subset_file.read_text())
    out = []
    for entry in data["tasks"]:
        pool = pools.get(f"{entry['repo']}/task{entry['task_id']}")
        if pool is None:
            continue
        for pair in entry["pairs"]:
            ids = [f for f in pair if f in pool.features]
            if len(ids) != 2 or k < 2:
                continue
            extras = [f for f in sorted(pool.features) if f not in ids]
            if len(extras) < k - 2:
                continue
            ids = ids + rng.sample(extras, k - 2)
            rng.shuffle(ids)
            out.append(Bundle(pool=pool, feature_ids=ids))
    return out
