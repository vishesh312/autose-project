"""Adapters for each agent CLI, written from docs/harnesses.md (see it for sources and UNVERIFIED marks).

Every adapter runs inside a container, so the CLIs' permission-bypass flags are only ever used in the
sandbox. Token convention: Usage.input = ALL prompt tokens (cached included), cached_input = cache reads.
Event/field names marked UNVERIFIED have not been captured from a live run; `parbench probe` shows raw output
under results/_probes/ so they can be fixed quickly.
"""

from __future__ import annotations

import json
import uuid

from ..config import ModelSpec, Usage
from ..sandbox import WORK, Container
from .base import Harness, ParsedRun, RunOptions, ToolCall

HOST = "host.docker.internal"


# =============================================================== Claude Code
class ClaudeHarness(Harness):
    name = "claude"
    supports_subagents = True
    providers = ("anthropic", "openai_compat")  # openai_compat only if the server has /v1/messages
    repo_artifacts = [".claude"]
    cost_is_cumulative = True  # on resume total_cost_usd already includes earlier runs
    forward_env = ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"]

    def setup(self, c, model, opts):
        env = {"IS_SANDBOX": "1", "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}
        if model.provider == "openai_compat":
            url = model.anthropic_base_url or ""
            env.update(ANTHROPIC_BASE_URL=url, ANTHROPIC_AUTH_TOKEN="local", ANTHROPIC_API_KEY="",
                       ANTHROPIC_MODEL=model.model, ANTHROPIC_DEFAULT_HAIKU_MODEL=model.model,
                       ANTHROPIC_DEFAULT_SONNET_MODEL=model.model, ANTHROPIC_DEFAULT_OPUS_MODEL=model.model,
                       CLAUDE_CODE_SUBAGENT_MODEL=model.model)
        if not opts.subagents:
            env["CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS"] = "1"
        return env

    def command(self, prompt_file, model, opts, resume_session):
        deny = "AskUserQuestion" + ("" if opts.subagents else ",Agent,Task")
        args = ["claude", "-p", self.prompt_arg(prompt_file), "--output-format", "stream-json", "--verbose",
                "--permission-mode", "bypassPermissions", "--model", self.q(model.model),
                "--disallowedTools", self.q(deny)]
        if opts.max_turns:
            args += ["--max-turns", str(opts.max_turns)]
        if resume_session:
            args += ["--resume", resume_session]
        return " ".join(args)

    def parse(self, stdout, stderr):
        run, seen_calls = ParsedRun(), set()
        for ev in self.jsonl(stdout):
            t = ev.get("type")
            if t == "system" and ev.get("subtype") == "init":
                run.session_id = ev.get("session_id")
            elif t == "assistant":
                msg = ev.get("message", {})
                for blk in msg.get("content", []):
                    if blk.get("type") == "tool_use" and blk.get("id") not in seen_calls:
                        seen_calls.add(blk.get("id"))
                        tc = ToolCall(blk.get("name", ""), blk.get("input", {}) or {})
                        run.tool_calls.append(tc)
                        if tc.name in ("Agent", "Task"):
                            run.subagent_calls += 1
                        if tc.name == "AskUserQuestion":
                            run.asked_question = True
            elif t == "result":
                run.session_id = ev.get("session_id") or run.session_id
                run.final_text = ev.get("result") or ""
                run.num_turns = ev.get("num_turns")
                if ev.get("is_error") or str(ev.get("subtype", "")).startswith("error"):
                    run.error = str(ev.get("subtype"))
                mu = ev.get("modelUsage") or {}
                u = Usage(calls=ev.get("num_turns") or 0, cost_reported=ev.get("total_cost_usd"))
                if mu:  # includes subagent tokens
                    for m in mu.values():
                        cr, cw = m.get("cacheReadInputTokens", 0), m.get("cacheCreationInputTokens", 0)
                        u.input += m.get("inputTokens", 0) + cr + cw
                        u.cached_input += cr
                        u.cache_write += cw
                        u.output += m.get("outputTokens", 0)
                else:
                    x = ev.get("usage") or {}
                    cr, cw = x.get("cache_read_input_tokens", 0), x.get("cache_creation_input_tokens", 0)
                    u.input = x.get("input_tokens", 0) + cr + cw
                    u.cached_input, u.cache_write, u.output = cr, cw, x.get("output_tokens", 0)
                run.usage = u
        return run


# =============================================================== Codex CLI
class CodexHarness(Harness):
    name = "codex"
    supports_subagents = True
    providers = ("openai", "openai_compat")  # openai_compat needs a /v1/responses endpoint
    repo_artifacts = []
    usage_is_cumulative = True  # thread-level running total
    forward_env = ["CODEX_API_KEY", "OPENAI_API_KEY"]
    auth_files = [("~/.codex/auth.json", "/parbench/codex/auth.json")]  # only with copy_auth_files

    def setup(self, c, model, opts):
        toml = []
        if model.provider == "openai_compat":
            toml += ['model_provider = "local"', "[model_providers.local]", 'name = "local"',
                     f'base_url = "{model.base_url}"', 'wire_api = "responses"']
            if model.api_key_env:
                toml.append(f'env_key = "{model.api_key_env}"')
        toml.insert(0, "")
        c.put_file(f"{WORK}/codex/config.toml", "\n".join(toml) + "\n")
        env = {"CODEX_HOME": f"{WORK}/codex"}
        if model.provider == "openai_compat" and not model.api_key_env:
            env["LOCAL_API_KEY"] = "local"
            c.put_file(f"{WORK}/codex/config.toml", "\n".join(toml + ['env_key = "LOCAL_API_KEY"']) + "\n")
        return env

    def command(self, prompt_file, model, opts, resume_session):
        flags = ["--json", "--skip-git-repo-check", "-s", "danger-full-access", "-C", "/workspace/repo",
                 "-m", self.q(model.model), "-c", "project_doc_max_bytes=0",
                 "-c", "tools.experimental_request_user_input.enabled=false"]
        if model.reasoning_effort:
            flags += ["-c", f"model_reasoning_effort={model.reasoning_effort}"]
        if not opts.subagents:
            flags += ["-c", "agents.enabled=false", "--disable", "multi_agent"]
        base = "codex exec " + " ".join(flags)
        if resume_session:
            return f'{base} resume {resume_session} {self.prompt_arg(prompt_file)}'
        return f'{base} {self.prompt_arg(prompt_file)}'

    def parse(self, stdout, stderr):
        run = ParsedRun()
        last_usage, turns = None, 0
        for ev in self.jsonl(stdout):
            t = ev.get("type")
            if t == "thread.started":
                run.session_id = ev.get("thread_id")
            elif t == "turn.completed":
                turns += 1
                last_usage = ev.get("usage")
            elif t in ("turn.failed", "error"):
                run.error = json.dumps(ev)[:300]
            elif t == "item.completed":
                it = ev.get("item", {})
                ty = it.get("type")
                if ty == "agent_message":
                    run.final_text = it.get("text", "")
                elif ty == "command_execution":
                    run.tool_calls.append(ToolCall("shell", {"command": it.get("command", "")}, it.get("exit_code") == 0))
                elif ty == "file_change":
                    for ch in it.get("changes", []):
                        run.tool_calls.append(ToolCall("edit", {"path": ch.get("path", "")}))
                elif ty == "collab_tool_call":
                    run.subagent_calls += 1
                    run.tool_calls.append(ToolCall("subagent", {"tool": it.get("tool")}))
                elif ty == "mcp_tool_call":
                    run.tool_calls.append(ToolCall(it.get("tool", "mcp"), it.get("arguments") or {}))
        if last_usage:
            run.usage = Usage(
                input=last_usage.get("input_tokens", 0), cached_input=last_usage.get("cached_input_tokens", 0),
                cache_write=last_usage.get("cache_write_input_tokens", 0), output=last_usage.get("output_tokens", 0),
                reasoning=last_usage.get("reasoning_output_tokens", 0), calls=turns)
        run.num_turns = turns
        return run


# =============================================================== OpenCode
class OpenCodeHarness(Harness):
    name = "opencode"
    supports_subagents = True
    providers = ("openai_compat", "anthropic", "openai", "google", "openrouter")
    repo_artifacts = [".opencode", "opencode.json", "opencode.jsonc"]

    def setup(self, c, model, opts):
        rules = [{"action": "question", "resource": "*", "effect": "deny"}]
        if not opts.subagents:
            rules += [{"action": "subagent", "resource": "*", "effect": "deny"},
                      {"action": "execute", "resource": "*", "effect": "deny"}]
        steps = {"steps": opts.max_turns} if opts.max_turns else {}
        cfg = {
            "model": f"{self._prov(model)}/{model.model}",
            "snapshots": False,
            "permissions": rules,  # UNVERIFIED location; also repeated under agents.build per docs/harnesses.md
            "agents": {"build": {"permissions": rules, **steps}},
        }
        if model.provider == "openai_compat":
            cfg["providers"] = {"local": {"package": "@opencode/ai/providers/openai-compatible",
                                          "settings": {"baseURL": model.base_url, "apiKey": "local"}}}
        c.put_file(f"{WORK}/opencode.json", json.dumps(cfg, indent=2))
        return {"OPENCODE_CONFIG_CONTENT": json.dumps(cfg), "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
                "PWD": "/workspace/repo"}

    @staticmethod
    def _prov(model):
        return {"openai_compat": "local"}.get(model.provider, model.provider)

    def command(self, prompt_file, model, opts, resume_session):
        a = f"opencode run --standalone --auto --format json -m {self.q(self._prov(model) + '/' + model.model)}"
        if resume_session:
            a += f" -s {resume_session}"
        return f"{a} {self.prompt_arg(prompt_file)} </dev/null"

    def parse(self, stdout, stderr):
        run, u = ParsedRun(), Usage()
        for ev in self.jsonl(stdout):
            t, part = ev.get("type"), ev.get("part", {}) or {}
            run.session_id = ev.get("sessionID") or run.session_id
            if t == "text":
                run.final_text = part.get("text", "")
            elif t == "tool_use":
                st = part.get("state", {}) or {}
                tc = ToolCall(part.get("tool", ""), st.get("input", {}) or {}, st.get("status") == "completed")
                run.tool_calls.append(tc)
                if tc.name == "subagent":
                    run.subagent_calls += 1
                if tc.name in ("question", "ask"):
                    run.asked_question = True
            elif t == "step_finish":
                tk = part.get("tokens", {}) or {}
                cache = tk.get("cache", {}) or {}
                cr, cw = cache.get("read", 0), cache.get("write", 0)
                u = u + Usage(input=tk.get("input", 0) + cr + cw, cached_input=cr, cache_write=cw,
                              output=tk.get("output", 0), reasoning=tk.get("reasoning", 0),
                              cost_reported=part.get("cost"), calls=1)
            elif t == "error":
                run.error = json.dumps(ev)[:300]
        run.usage, run.num_turns = u, u.calls
        return run


# =============================================================== Pi
class PiHarness(Harness):
    name = "pi"
    supports_subagents = False
    providers = ("openai_compat", "anthropic", "openai", "google", "openrouter")
    repo_artifacts = [".pi"]
    auth_files = [("~/.pi/agent/auth.json", "/parbench/pi/auth.json")]

    def setup(self, c, model, opts):
        env = {"PI_OFFLINE": "1", "PI_CODING_AGENT_DIR": f"{WORK}/pi"}
        models = {"providers": {}}
        if model.provider == "openai_compat":
            models["providers"]["local"] = {
                "baseUrl": model.base_url, "api": "openai-completions", "apiKey": "local",
                "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
                "models": [{"id": model.model, "contextWindow": model.context, "maxTokens": model.max_output}]}
        c.put_file(f"{WORK}/pi/models.json", json.dumps(models, indent=2))
        self._sid = uuid.uuid4().hex
        return env

    def command(self, prompt_file, model, opts, resume_session):
        prov = "local" if model.provider == "openai_compat" else model.provider
        sid = resume_session or getattr(self, "_sid", uuid.uuid4().hex)
        think = f" --thinking {model.reasoning_effort}" if model.reasoning_effort else ""
        return (f"pi --mode json --session-id {sid} --model {self.q(prov + '/' + model.model)}{think} "
                f"--no-context-files --no-skills --no-extensions -na "
                f"--tools read,bash,edit,write,grep,find,ls {self.prompt_arg(prompt_file)}")

    def parse(self, stdout, stderr):
        run, u = ParsedRun(), Usage()
        for ev in self.jsonl(stdout):
            t = ev.get("type")
            if t == "session":
                run.session_id = ev.get("id")
            elif t == "tool_execution_start":
                run.tool_calls.append(ToolCall(ev.get("toolName", ""), ev.get("args", {}) or {}))
            elif t == "message_end":
                m = ev.get("message", {}) or {}
                if m.get("role") != "assistant":
                    continue
                for blk in m.get("content", []) if isinstance(m.get("content"), list) else []:
                    if blk.get("type") == "text":
                        run.final_text = blk.get("text", "")
                us = m.get("usage") or {}
                cr, cw = us.get("cacheRead", 0), us.get("cacheWrite", 0)
                u = u + Usage(input=us.get("input", 0) + cr + cw, cached_input=cr, cache_write=cw,
                              output=us.get("output", 0), reasoning=us.get("reasoning", 0) or 0,
                              cost_reported=(us.get("cost") or {}).get("total"), calls=1)
                if m.get("stopReason") == "error" or m.get("errorMessage"):
                    run.error = str(m.get("errorMessage") or m.get("stopReason"))
        run.usage, run.num_turns = u, u.calls
        return run


# =============================================================== Antigravity (agy)
class AgyHarness(Harness):
    name = "agy"
    supports_subagents = True
    providers = ("antigravity", "google")
    repo_artifacts = [".gemini", ".agents", ".agent", ".metadata.json"]
    forward_env = ["GEMINI_API_KEY"]

    def setup(self, c, model, opts):
        return {}

    def command(self, prompt_file, model, opts, resume_session):
        # agy requires the prompt attached to -p (verified: `-p --output-format` mis-parses).
        a = f"agy --output-format stream-json --dangerously-skip-permissions --model {self.q(model.model)}"
        if not opts.subagents:
            a += " --agent nosub"  # custom agent without subagent tools; see docs/harnesses.md (UNVERIFIED)
        a += f" --print-timeout {max(1, opts.timeout_s // 60)}m"
        if resume_session:
            a += f" --conversation {resume_session}"
        return f'{a} -p "$(cat {self.q(prompt_file)})"'

    def parse(self, stdout, stderr):
        run, u = ParsedRun(), Usage()
        for ev in self.jsonl(stdout):
            e = ev.get("event")
            if e == "step_update":
                su = ev.get("step_update", {})
                run.session_id = su.get("conversation_id") or run.session_id
                ti = su.get("tool_info")
                if su.get("step_type") == "tool" and su.get("state") == "ACTIVE" and ti:
                    tc = ToolCall(ti.get("name", ""), ti.get("parameters", {}) or {})
                    run.tool_calls.append(tc)
                    if "subagent" in tc.name:
                        run.subagent_calls += 1
                    if tc.name in ("ask_question", "ask_permission"):
                        run.asked_question = True
            elif e == "result":
                r = ev.get("result", {})
                run.session_id = r.get("conversation_id") or run.session_id
                run.final_text = r.get("response", "")
                run.num_turns = r.get("num_turns")
                x = r.get("usage") or {}
                cr = x.get("cache_read_tokens", 0)
                u = Usage(input=x.get("input_tokens", 0) + cr, cached_input=cr, output=x.get("output_tokens", 0),
                          reasoning=x.get("thinking_tokens", 0), calls=r.get("num_turns") or 0)
                if r.get("status") == "WAITING":
                    run.asked_question = True
                if r.get("status") not in ("SUCCESS", "WAITING"):
                    run.error = str(r.get("status"))
                if r.get("denied_actions"):
                    run.error = (run.error or "") + f" denied_actions={r['denied_actions']}"
        run.usage = u
        return run


# =============================================================== Gemini CLI (fallback for agy)
class GeminiHarness(Harness):
    name = "gemini"
    supports_subagents = True
    providers = ("google",)
    repo_artifacts = [".gemini"]
    forward_env = ["GEMINI_API_KEY"]
    auth_files = [("~/.gemini/oauth_creds.json", "/parbench/gemini/.gemini/oauth_creds.json")]

    def setup(self, c, model, opts):
        settings = {"model": {"maxSessionTurns": opts.max_turns or -1}, "tools": {"exclude": ["ask_user"]}}
        if not opts.subagents:
            settings["agents"] = {"overrides": {n: {"enabled": False}
                                                for n in ("codebase_investigator", "cli_help", "generalist")}}
        c.put_file(f"{WORK}/gemini/.gemini/settings.json", json.dumps(settings))
        return {"GEMINI_CLI_HOME": f"{WORK}/gemini"}

    def command(self, prompt_file, model, opts, resume_session):
        a = f"gemini -o stream-json --approval-mode yolo -m {self.q(model.model)}"
        if resume_session:
            a += f" --resume {resume_session}"
        return f'{a} -p "$(cat {self.q(prompt_file)})"'

    def parse(self, stdout, stderr):
        run, text = ParsedRun(), []
        for ev in self.jsonl(stdout):
            t = ev.get("type")
            if t == "init":
                run.session_id = ev.get("session_id")
            elif t == "message" and ev.get("role") == "assistant":
                text.append(ev.get("content", ""))
            elif t == "tool_use":
                run.tool_calls.append(ToolCall(ev.get("tool_name", ""), ev.get("parameters", {}) or {}))
            elif t == "error":
                run.error = json.dumps(ev)[:300]
            elif t == "result":
                st = ev.get("stats", {}) or {}
                run.usage = Usage(input=st.get("input_tokens", 0), cached_input=st.get("cached", 0),
                                  output=st.get("output_tokens", 0), calls=st.get("tool_calls", 0))
        run.final_text = "".join(text)
        return run
