"""Run one agent (one harness session) inside a container, with nudges, timing and full logging."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import ModelSpec, Usage
from .harnesses.base import Harness, ParsedRun, RunOptions, looks_like_question
from .prompts import render
from .sandbox import Container


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
    infra_retries: int = 0  # waits for quota/capacity errors (not nudges)
    infra_wait_s: float = 0.0
    infra_failed: bool = False  # ended on a service error after all retries: the run is not a valid measurement
    context_exceeded: bool = False  # an attempt ended on a context-length error (valid outcome, not infra)
    accounts: list[int] = field(default_factory=list)  # agy accounts used, in order (1-based position in configs/agy_accounts.yaml)
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


MAX_INFRA_RETRIES = 8
# Service problems, not agent outcomes: quota/capacity (agy), and a model server that is down or failing (OpenCode
# + vLLM/Ollama, checked live with OpenCode 2.2.4: `provider.transport` "ECONNREFUSED: Unable to connect", and
# `provider.internal` with "status":502 from a server answering 502).
_INFRA = re.compile(
    r"RESOURCE_EXHAUSTED|UNAVAILABLE|quota reached|No capacity|high traffic|overloaded|rate.?limit"
    r"|ECONNREFUSED|ECONNRESET|connection refused|Unable to connect|provider\.transport|bad gateway"
    r"|service unavailable|gateway time-?out|\b(?:429|500|502|503|504)\b", re.I)
# Context overflow is a model/harness outcome (valid run), only recorded. OpenCode 2.x reports a vLLM
# "maximum context length" 400 as `compaction.failed` after trying to compact (checked live).
_CONTEXT = re.compile(r"maximum context length|context.length.exceeded|context window|compaction\.failed|"
                      r"prompt is too long|too many tokens", re.I)


_CONN = re.compile(r"ECONNREFUSED|connection refused|Unable to connect", re.I)


def service_error(parsed: ParsedRun, r) -> str | None:
    """The error text to check for infra problems: the parsed error, else a connection error on the stderr of a
    failed command (only connection patterns there: stderr is free text, a bare "500" could be anything)."""
    if parsed.error:
        return parsed.error
    tail = r.stderr[-2000:] if r.returncode and not r.timed_out else ""
    return tail if _CONN.search(tail) else None


def infra_wait_s(error: str | None, retry_no: int) -> int | None:
    """Seconds to wait if `error` is a retryable service problem (quota, capacity, rate limit), else None."""
    if not error or not _INFRA.search(error) or _CONTEXT.search(error):
        return None
    m = re.search(r"[Rr]esets? in (?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?", error)
    if m and any(m.groups()):
        h, mi, se = (int(x or 0) for x in m.groups())
        return min(h * 3600 + mi * 60 + se + 30, 7200)
    return min(60 * retry_no, 300)


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
    if "PARBENCH_AGY_ACCOUNT" in harness_env:
        rec.accounts.append(int(harness_env["PARBENCH_AGY_ACCOUNT"]))
    (log_dir / "prompt.md").write_text(prompt)

    rec.started = time.time()
    session: str | None = None
    current_prompt = prompt
    all_calls = []
    prev_cum = Usage()
    deadline = rec.started + opts.timeout_s
    i, nudges_used, infra_retries = 0, 0, 0
    while True:
        prompt_file = f"{c.work}/{agent_id}.prompt{i}.md"
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

        # Quota or sign-in error on one of several accounts (agy; parbench/agy_accounts.py): move to a free
        # account at once, without waiting. A conversation lives in its account's profile, so the new
        # account starts a fresh session with the original prompt in the same (partly edited) repo.
        switch = getattr(harness, "switch_account", None)
        new_env = None
        if switch and not r.timed_out and infra_retries < MAX_INFRA_RETRIES:
            new_env = switch(harness_env, parsed.error or (r.stderr[-2000:] if r.returncode else None))
        if new_env is not None:
            infra_retries += 1
            rec.infra_retries += 1
            rec.attempts.append(
                Attempt(i, r.started, r.ended, r.returncode, r.timed_out, parsed.usage.to_json(), parsed.num_turns,
                        parsed.session_id, f"account_switch_to_{new_env.get('PARBENCH_AGY_ACCOUNT')}",
                        parsed.final_text[-1500:], parsed.error)
            )
            harness_env = {**(env or {}), **new_env}
            rec.accounts.append(int(new_env["PARBENCH_AGY_ACCOUNT"]))
            session, current_prompt, prev_cum = None, prompt, Usage()
            i += 1
            continue

        # Retryable service problem (quota / capacity): wait, then resume. Does not use up a nudge, and the
        # waiting time does not count against the agent's own time limit.
        err = service_error(parsed, r)
        wait = None if r.timed_out else infra_wait_s(err, infra_retries + 1)
        if wait is not None and infra_retries < MAX_INFRA_RETRIES:
            infra_retries += 1
            rec.infra_retries += 1
            rec.attempts.append(
                Attempt(i, r.started, r.ended, r.returncode, r.timed_out, parsed.usage.to_json(), parsed.num_turns,
                        parsed.session_id, f"infra_retry_in_{wait}s", parsed.final_text[-1500:], err)
            )
            rec.infra_wait_s += wait
            time.sleep(wait)
            deadline += wait
            current_prompt = (render("nudge", reason="a temporary service error interrupted you", repo=c.repo)
                              if session else prompt)
            i += 1
            continue

        reason = None
        if not r.timed_out and nudges_used < max_nudges and time.time() < deadline - 60:
            reason = _nudge_reason(c, parsed, base_sha)
            if reason and not session:
                reason = f"{reason} (no session id; cannot resume)"
        rec.attempts.append(
            Attempt(i, r.started, r.ended, r.returncode, r.timed_out, parsed.usage.to_json(), parsed.num_turns,
                    parsed.session_id, reason, parsed.final_text[-1500:], parsed.error)
        )
        if err and not rec.error:
            rec.error = err
        rec.infra_failed = infra_wait_s(err, 1) is not None  # still a service error after all retries
        rec.context_exceeded |= bool(err and _CONTEXT.search(err))  # a valid outcome, recorded only
        if not reason or not session:
            break
        nudges_used += 1
        rec.nudges += 1
        current_prompt = render("nudge", reason=reason, repo=c.repo)
        i += 1

    rec.ended = time.time()
    rec.cost_list = model.list_cost(rec.usage)
    for tc in all_calls:
        rec.tool_calls[tc.kind] = rec.tool_calls.get(tc.kind, 0) + 1
        if tc.kind == "read":
            rec.files_read += tc.files
        elif tc.kind == "edit":
            rec.files_edited += tc.files
    prefix = c.repo.rstrip("/") + "/"
    rec.files_read = sorted(set(_norm(p, prefix) for p in rec.files_read))
    rec.files_edited = sorted(set(_norm(p, prefix) for p in rec.files_edited))
    with open(log_dir / "tool_calls.jsonl", "w") as f:
        for tc in all_calls:
            f.write(json.dumps({"name": tc.name, "kind": tc.kind, "args": tc.args, "ok": tc.ok, "ts": tc.ts}) + "\n")
    (log_dir / "record.json").write_text(json.dumps(rec.to_json(), indent=2))
    return rec


def _norm(p: str, prefix: str) -> str:
    return p.removeprefix(prefix).removeprefix("./")


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
