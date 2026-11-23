"""A model server that is down or failing is an infra error (retry, then infra_failed); context overflow is not.

Uses a fake harness and workspace (no Docker, no model). The error strings are the ones OpenCode 2.2.4 printed
against a dead port, a server answering 502, and a vLLM-style "maximum context length" 400 (checked 2026-11-23).
"""

import time

import pytest

from parbench import agent_runner
from parbench.agent_runner import infra_wait_s, run_agent
from parbench.config import ModelSpec, Usage
from parbench.harnesses.base import Harness, ParsedRun, RunOptions
from parbench.sandbox import ExecResult

REFUSED = ('{"type": "error", "sessionID": "ses_x", "error": {"type": "provider.transport", '
           '"message": "ECONNREFUSED: Unable to connect. Is the computer able to access the url?"}}')
BAD_GW = ('{"type": "error", "sessionID": "ses_x", "error": {"type": "provider.internal", "message": "bad gateway", '
          '"status": 502}}')
CONTEXT = ('{"type": "error", "sessionID": "ses_x", "error": {"type": "compaction.failed", "message": "The '
           'compaction request cannot be reduced further without losing the latest exchange or checkpoint"}}')


@pytest.mark.parametrize("err", [REFUSED, BAD_GW, "HTTP 503 Service Unavailable", "connection refused"])
def test_server_down_is_infra(err):
    assert infra_wait_s(err, 1) is not None


@pytest.mark.parametrize("err", [CONTEXT, "This model's maximum context length is 32768 tokens (code 500)",
                                 "tool failed: exit status 1", None, "session 1795443500 ended"])
def test_not_infra(err):
    assert infra_wait_s(err, 1) is None


class FakeWorkspace:
    repo, work = "/ws/repo", "/ws/work"

    def __init__(self):
        self.files = {}

    def put_file(self, path, content, mode=None):
        self.files[path] = content

    def exec(self, cmd, *, timeout=None, env=None, stdout_path=None, stderr_path=None, workdir=None):
        if cmd.startswith("git"):
            return ExecResult(0, "changed\n", "", time.time(), time.time())
        out = FakeHarness.script.pop(0)
        for p, t in ((stdout_path, out), (stderr_path, "")):
            if p:
                p.write_text(t)
        return ExecResult(1 if out.startswith("ERR") else 0, out, "", time.time(), time.time())


class FakeHarness(Harness):
    name = "fake"
    script: list[str] = []

    def setup(self, c, model, opts):
        return {}

    def command(self, prompt_file, model, opts, resume_session):
        return f"fake {prompt_file}"

    def parse(self, stdout, stderr):
        err = stdout[3:] if stdout.startswith("ERR") else None
        return ParsedRun(session_id="ses_x", usage=Usage(input=10, output=1, calls=1), final_text="done", error=err)


def _run(tmp_path, script):
    FakeHarness.script = list(script)
    return run_agent(FakeWorkspace(), FakeHarness(), ModelSpec(id="m", provider="openai_compat", model="m"),
                     "do it", RunOptions(False, 10, 600), tmp_path, agent_id="a", role="worker", feature_ids=[1],
                     max_nudges=0, base_sha="abc")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(agent_runner.time, "sleep", lambda s: None)


def test_recovers_after_server_comes_back(tmp_path):
    rec = _run(tmp_path, ["ERR" + REFUSED, "ERR" + BAD_GW, "ok"])
    assert rec.infra_retries == 2 and not rec.infra_failed and rec.attempts[-1].nudge_reason is None
    # every prompt sent is logged per attempt: the task, then the resume messages after each service error
    assert (tmp_path / "attempt0.prompt.md").read_text() == "do it"
    assert "temporary service error" in (tmp_path / "attempt2.prompt.md").read_text()


def test_server_down_for_good_is_infra_failed(tmp_path):
    rec = _run(tmp_path, ["ERR" + REFUSED] * (agent_runner.MAX_INFRA_RETRIES + 1))
    assert rec.infra_failed and rec.infra_retries == agent_runner.MAX_INFRA_RETRIES


def test_context_overflow_is_valid_but_recorded(tmp_path):
    rec = _run(tmp_path, ["ERR" + CONTEXT])
    assert not rec.infra_failed and rec.infra_retries == 0 and rec.context_exceeded
