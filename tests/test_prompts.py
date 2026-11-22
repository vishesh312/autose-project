"""Every strategy's prompt renders fully (no ${...} left) with the workspace's repo path."""

import pytest

from parbench import prompts
from parbench.config import ROOT
from parbench.dataset import load_pools
from parbench.strategies import StrategySpec

REPO = "/tmp/parbench-host-x/repo"
FEATS = list(load_pools(ROOT / "smoke" / "dataset")["toy_task/task1"].features.values())[:3]


def _check(text: str) -> None:
    assert "${" not in text and REPO in text and "/workspace/repo" not in text


@pytest.mark.parametrize("extras", [[], ["plan_first"], ["small_model"], ["plan_first", "small_model"]])
def test_single_and_multi(extras):
    s = prompts.single_task(FEATS[0], extra=extras, repo=REPO)
    _check(s)
    for name in ("multi_task", "harness_native", "harness_native_encourage", "harness_native_worktrees"):
        m = prompts.multi_task(FEATS, name, extra=extras, repo=REPO)
        _check(m)
        assert m.count("### Task") == len(FEATS)
    for e in extras:
        assert prompts.template(e).strip() in s and prompts.template(e).strip() in m


def test_resolver_and_nudge():
    _check(prompts.resolver(FEATS, ["a.py"], repo=REPO))
    _check(prompts.render("nudge", reason="x", repo=REPO))


def test_spec_parse():
    s = StrategySpec.parse("S4@harness_native_worktrees+plan_first+small_model")
    assert (s.id, s.template, s.extras) == ("S4", "harness_native_worktrees", ["plan_first", "small_model"])
    assert s.label == "S4@harness_native_worktrees+plan_first+small_model"
