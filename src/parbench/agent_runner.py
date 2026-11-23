"""Run one agent (one harness session) inside a container, with nudges, timing and full logging."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import ModelSpec, Usage
from . import meter
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
    proxy_usage: dict | None = None  # meter (server-side) usage of this attempt's requests


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
    usage: Usage = field(default_factory=Usage)  # harness-reported (all attempts, failed ones included)
    usage_subagents: Usage = field(default_factory=Usage)  # part of `usage` from child sessions read from their logs (agy)
    usage_failed_attempts: Usage = field(default_factory=Usage)  # part of `usage` spent in attempts that ended on a
                                                                 # quota/capacity error or account switch
    usage_proxy: Usage | None = None  # from the metering proxy (parbench/meter.py), if one was in front of the model
    meter: dict | None = None  # proxy request counts: total, failed, usage_missing, by kind
    token_source: str = "harness"  # "proxy" when usage_proxy is complete (no request without usage)
    cost_list: float | None = None
    nudges: int = 0
    infra_retries: int = 0  # waits for quota/capacity errors (not nudges)
    infra_wait_s: float = 0.0
    infra_failed: bool = False  # ended on a service error after all retries: the run is not a valid measurement
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
        for k in ("usage", "usage_subagents", "usage_failed_attempts", "usage_proxy"):
            d[k] = getattr(self, k).to_json() if getattr(self, k) is not None else None
        return d

    @property
    def best_usage(self) -> Usage:
        """The usage metrics should use: proxy when complete, else harness-reported."""
        return self.usage_proxy if self.token_source == "proxy" and self.usage_proxy is not None else self.usage


MAX_INFRA_RETRIES = 8
_INFRA = re.compile(
    r"RESOURCE_EXHAUSTED|UNAVAILABLE|quota reached|No capacity|high traffic|overloaded|rate.?limit|\b(?:429|503)\b", re.I)


def infra_wait_s(error: str | None, retry_no: int) -> int | None:
    """Seconds to wait if `error` is a retryable service problem (quota, capacity, rate limit), else None."""
    if not error or not _INFRA.search(error):
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
    (log_dir / "meter.jsonl").unlink(missing_ok=True)
    tag = f"{agent_id}-{uuid.uuid4().hex[:8]}"
    m, model = meter.for_agent(model, tag, log_dir / "meter.jsonl")  # per-agent URL on the run's meter, if any
    n_req = 0
    harness_env = {**(env or {}), **harness.setup(c, model, opts)}
    if "PARBENCH_AGY_ACCOUNT" in harness_env:
        rec.accounts.append(int(harness_env["PARBENCH_AGY_ACCOUNT"]))
    (log_dir / "prompt.md").write_text(prompt)

    rec.started = time.time()
    session: str | None = None
    current_prompt = prompt
    all_calls = []
    prev_cum = Usage()
    sub_seen: dict[str, Usage] = {}
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
        resumed = session
        session = parsed.session_id or session
        delta = parsed.usage
        if harness.usage_is_cumulative:
            if parsed.session_id and parsed.session_id != resumed:
                prev_cum = Usage()  # a new session starts its running total at zero
            delta, prev_cum = parsed.usage - prev_cum, parsed.usage
        if harness.cost_is_cumulative and parsed.usage.cost_reported is not None:
            # reported cost is a running total: keep the latest as the record's total, tokens still add up
            cost_total = parsed.usage.cost_reported
            delta = Usage(delta.input, delta.cached_input, delta.cache_write, delta.output, delta.reasoning, None, delta.calls)
        for conv, cu in parsed.subagent_usage.items():  # child sessions (agy S4): add what is new since last attempt
            new = cu - sub_seen.get(conv, Usage())
            delta, rec.usage_subagents, sub_seen[conv] = delta + new, rec.usage_subagents + new, cu
        rec.usage = rec.usage + delta
        if harness.cost_is_cumulative and parsed.usage.cost_reported is not None:
            rec.usage.cost_reported = cost_total
        rec.busy_s += r.ended - r.started
        rec.returncode = r.returncode
        rec.timed_out = r.timed_out
        rec.subagent_calls += parsed.subagent_calls
        proxy_att = None
        if m:
            pu, n_req = m.usage_of(tag, n_req)
            proxy_att = pu.to_json()
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
                Attempt(i, r.started, r.ended, r.returncode, r.timed_out, delta.to_json(), parsed.num_turns,
                        parsed.session_id, f"account_switch_to_{new_env.get('PARBENCH_AGY_ACCOUNT')}",
                        parsed.final_text[-1500:], parsed.error, proxy_att)
            )
            rec.usage_failed_attempts = rec.usage_failed_attempts + delta
            harness_env = {**(env or {}), **new_env}
            rec.accounts.append(int(new_env["PARBENCH_AGY_ACCOUNT"]))
            session, current_prompt, prev_cum = None, prompt, Usage()
            i += 1
            continue

        # Retryable service problem (quota / capacity): wait, then resume. Does not use up a nudge, and the
        # waiting time does not count against the agent's own time limit.
        wait = None if r.timed_out else infra_wait_s(parsed.error, infra_retries + 1)
        if wait is not None and infra_retries < MAX_INFRA_RETRIES:
            infra_retries += 1
            rec.infra_retries += 1
            rec.attempts.append(
                Attempt(i, r.started, r.ended, r.returncode, r.timed_out, delta.to_json(), parsed.num_turns,
                        parsed.session_id, f"infra_retry_in_{wait}s", parsed.final_text[-1500:], parsed.error, proxy_att)
            )
            rec.usage_failed_attempts = rec.usage_failed_attempts + delta
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
            Attempt(i, r.started, r.ended, r.returncode, r.timed_out, delta.to_json(), parsed.num_turns,
                    parsed.session_id, reason, parsed.final_text[-1500:], parsed.error, proxy_att)
        )
        if parsed.error and not rec.error:
            rec.error = parsed.error
        rec.infra_failed = infra_wait_s(parsed.error, 1) is not None  # still a service error after all retries
        if not reason or not session:
            break
        nudges_used += 1
        rec.nudges += 1
        current_prompt = render("nudge", reason=reason, repo=c.repo)
        i += 1

    rec.ended = time.time()
    if m:
        ms = m.summary(tag)
        rec.usage_proxy, rec.meter = Usage(**ms.pop("usage")), ms
        # proxy is the ground truth unless some model response carried no usage (then it is a lower bound too)
        rec.token_source = "proxy" if not ms["requests_usage_missing"] else "harness"
    rec.cost_list = model.list_cost(rec.best_usage)
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
