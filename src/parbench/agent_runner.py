"""Run one agent (one harness session) inside a container, with nudges, timing and full logging."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import ModelSpec, Usage
from .harnesses.base import Harness, ParsedRun, RunOptions, looks_like_question
from .prompts import render
from .sandbox import WORK, Container


@dataclass
class Attempt:
    index: int
    started: float
    ended: float
    returncode: int
    timed_out: bool
    usage: dict
    num_turns: int | None
    session_id: str | None
    nudge_reason: str | None  # why the NEXT attempt was triggered (None = finished)
    final_text_tail: str
    error: str | None


@dataclass
class AgentRecord:
    agent_id: str
    role: str  # worker | solo | resolver
    harness: str
    model: str
    feature_ids: list[int]
    started: float = 0.0
    ended: float = 0.0
    busy_s: float = 0.0  # sum of attempt durations (excludes container setup)
    usage: Usage = field(default_factory=Usage)
    cost_list: float | None = None
    nudges: int = 0
    timed_out: bool = False
    returncode: int | None = None
    tool_calls: dict[str, int] = field(default_factory=dict)  # by kind
    files_read: list[str] = field(default_factory=list)
    files_edited: list[str] = field(default_factory=list)
    subagent_calls: int = 0
    patch_lines: int = 0
    patch_files: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> dict:
        d = asdict(self)
        d["usage"] = self.usage.to_json()
        return d


def run_agent(
    c: Container,
    harness: Harness,
    model: ModelSpec,
    prompt: str,
    opts: RunOptions,
    log_dir: Path,
    *,
    agent_id: str,
    role: str,
    feature_ids: list[int],
    max_nudges: int = 2,
    base_sha: str | None = None,
    env: dict[str, str] | None = None,
) -> AgentRecord:
    log_dir.mkdir(parents=True, exist_ok=True)
    rec = AgentRecord(agent_id, role, harness.name, model.id, feature_ids)
    harness_env = {**(env or {}), **harness.setup(c, model, opts)}
    (log_dir / "prompt.md").write_text(prompt)

    rec.started = time.time()
    session: str | None = None
    current_prompt = prompt
    all_calls = []
    prev_cum = Usage()
    deadline = rec.started + opts.timeout_s
    for i in range(max_nudges + 1):
        prompt_file = f"{WORK}/{agent_id}.prompt{i}.md"
        c.put_file(prompt_file, current_prompt)
        remaining = max(60, int(deadline - time.time()))
        step_opts = RunOptions(opts.subagents, opts.max_turns, remaining)
        cmd = harness.command(prompt_file, model, step_opts, resume_session=session)
        (log_dir / f"attempt{i}.cmd.sh").write_text(cmd + "\n")
        r = c.exec(
            cmd,
            timeout=remaining,
            env=harness_env,
            stdout_path=log_dir / f"attempt{i}.stdout.jsonl",
            stderr_path=log_dir / f"attempt{i}.stderr.log",
        )
        parsed: ParsedRun = harness.parse(r.stdout, r.stderr)
        session = parsed.session_id or session
        delta = parsed.usage
        if harness.usage_is_cumulative:
            delta, prev_cum = parsed.usage - prev_cum, parsed.usage
        if harness.cost_is_cumulative and parsed.usage.cost_reported is not None:
            # reported cost is a running total: keep the latest as the record's total, tokens still add up
            cost_total = parsed.usage.cost_reported
            delta = Usage(delta.input, delta.cached_input, delta.cache_write, delta.output, delta.reasoning, None, delta.calls)
        rec.usage = rec.usage + delta
        if harness.cost_is_cumulative and parsed.usage.cost_reported is not None:
            rec.usage.cost_reported = cost_total
        rec.busy_s += r.ended - r.started
        rec.returncode = r.returncode
        rec.timed_out = r.timed_out
        rec.subagent_calls += parsed.subagent_calls
        all_calls += parsed.tool_calls

        reason = None
        if not r.timed_out and i < max_nudges and time.time() < deadline - 60:
            reason = _nudge_reason(c, parsed, base_sha)
            if reason and not session:
                reason = f"{reason} (no session id; cannot resume)"
        rec.attempts.append(
            Attempt(i, r.started, r.ended, r.returncode, r.timed_out, parsed.usage.to_json(), parsed.num_turns,
                    parsed.session_id, reason, parsed.final_text[-1500:], parsed.error)
        )
        if parsed.error and not rec.error:
            rec.error = parsed.error
        if not reason or not session:
            break
        rec.nudges += 1
        current_prompt = render("nudge", reason=reason)

    rec.ended = time.time()
    rec.cost_list = model.list_cost(rec.usage)
    for tc in all_calls:
        rec.tool_calls[tc.kind] = rec.tool_calls.get(tc.kind, 0) + 1
        if tc.kind == "read":
            rec.files_read += tc.files
        elif tc.kind == "edit":
            rec.files_edited += tc.files
    rec.files_read = sorted(set(_norm(p) for p in rec.files_read))
    rec.files_edited = sorted(set(_norm(p) for p in rec.files_edited))
    with open(log_dir / "tool_calls.jsonl", "w") as f:
        for tc in all_calls:
            f.write(json.dumps({"name": tc.name, "kind": tc.kind, "args": tc.args, "ok": tc.ok, "ts": tc.ts}) + "\n")
    (log_dir / "record.json").write_text(json.dumps(rec.to_json(), indent=2))
    return rec


def _norm(p: str) -> str:
    return p.removeprefix("/workspace/repo/").removeprefix("./")


def _nudge_reason(c: Container, parsed: ParsedRun, base_sha: str | None) -> str | None:
    if parsed.asked_question:
        return "asked_question_tool"
    if looks_like_question(parsed.final_text):
        return "ended_with_question"
    if base_sha:
        changed = c.exec(f"git status --porcelain | head -1; git diff --quiet {base_sha} || echo changed").stdout.strip()
        if not changed:
            return "no_changes"
    return None
