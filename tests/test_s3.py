"""S3 (plan, then schedule): plan parsing, grouping, planning quality, read-only planner, scheduling and fallback."""

import json
from types import SimpleNamespace

import pytest

from parbench import prompts, strategies as st
from parbench.agent_runner import AgentRecord
from parbench.config import ROOT
from parbench.dataset import load_pools
from parbench.harnesses.base import RunOptions
from parbench.harnesses.cli_agents import OpenCodeHarness

FEATS = list(load_pools(ROOT / "smoke" / "dataset")["toy_task/task1"].features.values())[:3]


# ---------------------------------------------------------------- parse_plan
def test_parse_plan_fenced_and_paths():
    text = 'Plan below.\n```json\n{"tasks": [{"id": "f1", "files": [{"path": "/tmp/parbench-host-x/repo/src/a.py"},' \
           ' {"path": "./src/b.py"}]}, {"id": "Task 4", "files": ["src/a.py"]}]}\n```'
    assert st.parse_plan(text, [1, 4]) == {1: ["src/a.py", "src/b.py"], 4: ["src/a.py"]}


def test_parse_plan_bare_json_and_missing_task():
    text = '{"tasks": [{"id": "f2", "files": [{"path": "x.py", "confidence": "low"}]}]}'
    assert st.parse_plan(text, [1, 2]) == {1: [], 2: ["x.py"]}  # left-out task: no files, own group


@pytest.mark.parametrize("text", ["", "I could not decide.", '{"files": []}', '{"tasks": [{"id": "f9"}]}',
                                  '```json\n{"tasks": [ broken\n```'])
def test_parse_plan_bad_answers_raise(text):
    with pytest.raises(ValueError):
        st.parse_plan(text, [1, 2])


# ---------------------------------------------------------------- grouping
def test_groups_connected_components_keep_seeded_order():
    files = {3: ["a.py"], 1: ["b.py"], 4: ["a.py", "c.py"], 2: ["c.py"], 5: []}
    assert st.s3_groups(files, [3, 1, 4, 2, 5]) == [[3, 4, 2], [1], [5]]


def test_groups_all_disjoint_and_all_shared():
    assert st.s3_groups({1: ["a"], 2: ["b"]}, [1, 2]) == [[1], [2]]
    assert st.s3_groups({1: ["a"], 2: ["a"]}, [1, 2]) == [[1, 2]]


# ---------------------------------------------------------------- planning quality
def test_planning_quality():
    pred = {1: ["a.py", "x.py"], 2: ["a.py"], 3: ["c.py"]}
    gold = {1: ["a.py", "b.py"], 2: ["a.py"], 3: ["b.py"]}
    q = st.planning_quality(pred, gold, gold_conflicts={(1, 2)})
    assert q["file_recall"] == pytest.approx(2 / 4) and q["file_precision"] == pytest.approx(2 / 4)
    assert q["clash_vs_git_conflict"]["precision"] == 1.0 and q["clash_vs_git_conflict"]["recall"] == 1.0
    # gold files shared by (1,2) and (1,3); only (1,2) predicted
    assert q["clash_vs_shared_gold_file"]["recall"] == 0.5


# ---------------------------------------------------------------- prompt and read-only planner
def test_planner_prompt_renders():
    p = prompts.planner(FEATS, repo="/tmp/parbench-host-x/repo")
    assert "${" not in p and "/tmp/parbench-host-x/repo" in p and "/workspace/repo" not in p
    for f in FEATS:
        assert f"### Task f{f.fid}" in p
    assert "Do not edit anything" in p


def test_opencode_v1_read_only_config(monkeypatch):
    monkeypatch.setattr(OpenCodeHarness, "_v1", True)
    model = SimpleNamespace(provider="openai_compat", model="m", id="m", base_url="http://localhost:1/v1",
                            context=1000, max_output=None)
    c = SimpleNamespace(work="/tmp/w")

    def cfg(**kw):
        return json.loads(OpenCodeHarness()._setup_v1(c, model, RunOptions(**kw))["OPENCODE_CONFIG_CONTENT"])

    ro, normal = cfg(read_only=True), cfg()
    for t in ("edit", "write", "bash"):
        assert ro["tools"][t] is False and t not in normal["tools"]
    assert ro["permission"]["edit"] == ro["permission"]["bash"] == "deny"
    assert normal["permission"]["edit"] == "allow"


# ---------------------------------------------------------------- scheduling (agents faked, no model)
class FakeBox:
    def __init__(self):
        self.repo, self.work, self.done = "/tmp/fake/repo", "/tmp/fake/work", []

    def remove(self):
        pass

    def diff_against(self, base, exclude=None):
        return ""


@pytest.fixture
def fake_run(monkeypatch, tmp_path):
    bundle = SimpleNamespace(features=FEATS, feature_ids=[f.fid for f in FEATS],
                             pool=SimpleNamespace(id="toy_task/task1"))
    ctx = SimpleNamespace(bundle=bundle, harness=SimpleNamespace(supports_read_only=True, repo_artifacts=[]),
                          model=None, run_dir=tmp_path,
                          cfg=SimpleNamespace(max_turns=10, agent_timeout_s=60, max_nudges=0,
                                              dataset_path=lambda: tmp_path))
    calls = {"boxes": [], "agents": [], "merged": None, "s1": False}

    def container(ctx_, role):
        b = FakeBox()
        calls["boxes"].append((role, b))
        return b, "base"

    def agent(ctx_, c, base, prompt, *, agent_id, role, fids, subagents=False):
        c.done.append(fids[0])
        calls["agents"].append(agent_id)
        return AgentRecord(agent_id=agent_id, role=role, harness="h", model="m", feature_ids=fids)

    monkeypatch.setattr(st, "_container", container)
    monkeypatch.setattr(st, "_agent", agent)
    monkeypatch.setattr(st, "_collect", lambda ctx_, c, base, rec: "patch:" + ",".join(map(str, c.done)))

    def merge(ctx_, res, branches):
        calls["merged"] = branches
        res.finals["llm"] = "merged"
        return res

    monkeypatch.setattr(st, "_merge_stage", merge)
    return ctx, calls


def test_s3_oracle_schedules_groups_and_merges(fake_run, monkeypatch):
    ctx, calls = fake_run
    a, b, c = (f.fid for f in FEATS)
    gold = {a: ["x.py"], b: ["y.py"], c: ["x.py"]}
    for f in FEATS:
        monkeypatch.setattr(f, "gold_files", lambda f=f: gold[f.fid])
    res = st.run_s3(ctx, st.StrategySpec("S3", "oracle", []))
    assert res.s3["oracle"] and res.s3["groups"] == [[f"f{a}", f"f{c}"], [f"f{b}"]]
    groups = {tuple(box.done) for role, box in calls["boxes"] if role == "S3-group"}
    assert groups == {(a, c), (b,)}  # a and c run one after another in one workspace, b alone in parallel
    names = {n: (fids, p) for n, fids, p in calls["merged"]}
    assert names[f"g{a}-{c}"] == ([a, c], f"patch:{a},{c}") and names[f"g{b}"] == ([b], f"patch:{b}")
    assert [n for n, _, _ in res.worker_patches] == [f"f{a}", f"f{c}", f"f{b}"]


def test_s3_bad_plan_falls_back_to_s1(fake_run, monkeypatch):
    ctx, calls = fake_run
    monkeypatch.setattr(st, "run_agent", lambda *a, **k: AgentRecord(
        agent_id="planner", role="planner", harness="h", model="m", feature_ids=[]))
    monkeypatch.setattr(st, "_plan_text", lambda ctx_, rec: "sorry, no plan")

    def s1(ctx_, spec, *, subagents, default_tmpl):
        calls["s1"] = (spec.id, default_tmpl, subagents)
        r = st.StrategyResult()
        r.agents.append(AgentRecord(agent_id="solo", role="solo", harness="h", model="m", feature_ids=[]))
        r.finals["final"] = "p"
        return r

    monkeypatch.setattr(st, "run_single_session", s1)
    res = st.run_s3(ctx, st.StrategySpec("S3", None, []))
    assert calls["s1"] == ("S1", "multi_task", False)
    assert res.s3["fallback"] and "tasks" in res.s3["fallback_reason"]
    assert [r.agent_id for r in res.agents] == ["planner", "solo"]  # planner tokens still count


def test_plan_problem_and_planner_nudge_settings(fake_run, monkeypatch):
    ids = [f.fid for f in FEATS]
    assert st._plan_problem('{"tasks": [{"id": "f%d", "files": ["a.py"]}]}' % ids[0], ids) is None
    assert "plan JSON" in st._plan_problem("Here is the implementation: ...", ids)
    ctx, calls = fake_run
    seen = {}

    def fake_run_agent(*a, **k):
        seen.update(k)
        return AgentRecord(agent_id="planner", role="planner", harness="h", model="m", feature_ids=[])

    monkeypatch.setattr(st, "run_agent", fake_run_agent)
    monkeypatch.setattr(st, "_plan_text", lambda ctx_, rec: '{"tasks": [{"id": "f%d", "files": ["a.py"]}]}' % ids[0])
    res = st.run_s3(ctx, st.StrategySpec("S3", None, []))
    assert seen["base_sha"] is None  # no "no_changes" nudge for a read-only planner
    assert seen["nudge_template"] == "nudge_planner" and seen["check_final"]("no json") is not None
    assert seen["max_nudges"] == ctx.cfg.max_nudges + 1
    assert res.s3["planner_version"] == 2 and not res.s3["fallback"]


def test_nudge_planner_prompt_renders():
    from parbench.prompts import render
    p = render("nudge_planner", reason="x", repo="/r")
    assert "${" not in p and "only the plan JSON" in p and "implemented" not in p


def _planonly(fake_run, monkeypatch, plan_text):
    ctx, calls = fake_run
    monkeypatch.setattr(st, "run_agent", lambda *a, **k: AgentRecord(
        agent_id="planner", role="planner", harness="h", model="m", feature_ids=[]))
    monkeypatch.setattr(st, "_plan_text", lambda ctx_, rec: plan_text)
    return st.run_s3(ctx, st.StrategySpec.parse("S3@planonly")), calls


def test_planonly_one_group_is_not_executed(fake_run, monkeypatch):
    a, b, c = (f.fid for f in FEATS)
    res, calls = _planonly(fake_run, monkeypatch, json.dumps({"tasks": [{"id": f"f{x}", "files": ["same.py"]}
                                                                         for x in (a, b, c)]}))
    assert res.s3["executed"] is False and res.s3["groups"] == [[f"f{a}", f"f{b}", f"f{c}"]]
    assert "planning" in res.s3 and not res.finals and not res.worker_patches
    assert [r.agent_id for r in res.agents] == ["planner"] and not calls["agents"] and res.t_end >= res.t_start


def test_planonly_split_plan_is_executed(fake_run, monkeypatch):
    a, b, c = (f.fid for f in FEATS)
    res, calls = _planonly(fake_run, monkeypatch, json.dumps({"tasks": [
        {"id": f"f{a}", "files": ["x.py"]}, {"id": f"f{b}", "files": ["y.py"]}, {"id": f"f{c}", "files": ["x.py"]}]}))
    assert res.s3["executed"] is True and len(res.s3["groups"]) == 2
    assert sorted(calls["agents"]) == sorted([f"f{a}", f"f{b}", f"f{c}"]) and calls["merged"]


def test_planonly_no_plan_is_not_executed_and_no_s1(fake_run, monkeypatch):
    monkeypatch.setattr(st, "run_single_session", lambda *a, **k: pytest.fail("planonly must not fall back to S1"))
    res, calls = _planonly(fake_run, monkeypatch, "no plan here")
    assert res.s3["fallback"] and res.s3["executed"] is False and not calls["agents"]


def test_report_row_for_unexecuted_planonly():
    from parbench.report import flatten
    u = {"input": 10, "cached_input": 0, "output": 5, "reasoning": 0}
    rec = {"run": {"strategy": "S3@planonly", "harness": "h", "model": "m", "k": 2, "bundle": "b", "repeat": 0},
           "correctness": {"primary": "llm", "by_final": {}, "own_pass": {}},
           "cost": {"usage": u, "cost_usd": 0, "cost_per_solved_task": None, "coordination_overhead": 1.0,
                    "wasted_tokens": 0, "repeated_reads": []},
           "time": {"wall_clock_s": 1, "agent_busy_s": 1, "effective_parallelism": 1, "nudges": 0, "timeouts": 0},
           "s3": {"fallback": False, "executed": False, "groups": [["f1", "f2"]], "planner_nudges": 0,
                  "planning": {"file_recall": 1.0, "file_precision": 0.5, "clash_vs_shared_gold_file": {"recall": 1.0}}}}
    row = flatten(rec)
    assert row["s3_executed"] == 0 and row["task_pass_rate"] is None and row["plan_clash_found"] == 1.0
