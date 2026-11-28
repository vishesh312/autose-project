"""Pi adapter: per-agent session id and tools (via env, safe for parallel S2 agents), read-only planner, host mode."""

import json
from types import SimpleNamespace

from parbench.harnesses.base import RunOptions
from parbench.harnesses.cli_agents import PiHarness
from parbench.sandbox import HostWorkspace

MODEL = SimpleNamespace(provider="openai_compat", model="qwen3.8-pi", id="m", context=131072, max_output=None,
                        reasoning_effort=None, base_url="http://host.docker.internal:8002/v1")


class FakeBox:
    def __init__(self, work="/tmp/w"):
        self.work, self.files = work, {}

    def put_file(self, path, text):
        self.files[path] = text


def test_two_agents_get_own_sessions_and_tools():
    h, a, b = PiHarness(), FakeBox("/tmp/a"), FakeBox("/tmp/b")
    ea = h.setup(a, MODEL, RunOptions())
    eb = h.setup(b, MODEL, RunOptions(read_only=True))  # second setup must not change the first agent's values
    assert ea["PARBENCH_PI_SID"] != eb["PARBENCH_PI_SID"]
    assert ea["PARBENCH_PI_TOOLS"] == "read,bash,edit,write" and eb["PARBENCH_PI_TOOLS"] == "read,grep,find,ls"
    assert ea["PI_CODING_AGENT_DIR"] == "/tmp/a/pi" and "/tmp/a/pi/models.json" in a.files
    cmd = h.command("/tmp/a/p.md", MODEL, RunOptions(), None)
    assert '--session-id "$PARBENCH_PI_SID"' in cmd and '"${PARBENCH_PI_TOOLS:-read,bash,edit,write}"' in cmd
    assert "--session-id abc" in h.command("/tmp/a/p.md", MODEL, RunOptions(), "abc")


def test_host_mode_uses_localhost(monkeypatch):
    box = HostWorkspace.__new__(HostWorkspace)
    box.work, box.files = "/tmp/h", {}
    monkeypatch.setattr(HostWorkspace, "put_file", lambda self, p, t: self.files.__setitem__(p, t), raising=False)
    PiHarness().setup(box, MODEL, RunOptions())
    cfg = json.loads(box.files["/tmp/h/pi/models.json"])["providers"]["local"]
    assert cfg["baseUrl"] == "http://localhost:8002/v1" and cfg["api"] == "openai-completions"
    assert PiHarness.host_capable and PiHarness.supports_read_only and not PiHarness.supports_subagents
