# Harness reference: headless coding-agent CLIs in Docker

Generated 2026-11-06 for the eval pipeline (agents run headless in CooperBench per-pool containers, repo at `/workspace/repo`, JSON output parsed for metrics).

Versions covered (as installed on the dev Mac): OpenCode v2.2.4, Pi 0.84.4, Claude Code 2.1.319, Codex CLI 0.166.0, Antigravity `agy` 1.5.1, Gemini CLI 0.34.0 (fallback).

Legend: every fact is marked "verified (source)" or "UNVERIFIED". Where no marker is given inside a section, the section header's source list applies. No agent was run against a model with permissions bypassed during this research; only `--help`, `--version`, listing subcommands, file reads, package metadata and docs were used. Examples marked "adapted" or "illustrative" were not captured from a live run of that exact version.

## Summary matrix

| | Claude Code 2.1.319 | Codex 0.166.0 | OpenCode 2.2.4 | Pi 0.84.4 | agy 1.5.1 | Gemini CLI 0.34.0 |
|---|---|---|---|---|---|---|
| Install (Linux) | native binary `downloads.claude.ai/claude-code-releases/2.1.319/linux-{x64,arm64}[-musl]/claude`, or `npm i -g @anthropic-ai/claude-code@2.1.319` | `npm i -g @openai/codex@0.166.0` or release tarball `codex-{x86_64,aarch64}-unknown-linux-musl.tar.gz` (static musl, works on glibc too) | `@opencode/cli-linux-{x64,arm64}[-musl]@2.2.4` tarball (static binary) or `npm i -g @opencode/cli@2.2.4` | `npm i -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.4` (Node >=22.19) | `curl -fsSL https://antigravity.google/cli/install.sh \| bash`; Linux glibc+musl exist; only latest (1.5.2) served, cannot pin 1.5.1 | `npm i -g @google/gemini-cli@0.34.0` (Node >=20) |
| Headless | `claude -p "$P" --output-format stream-json --verbose --permission-mode bypassPermissions` (root needs `IS_SANDBOX=1`) | `codex exec --json -C DIR --skip-git-repo-check -s danger-full-access "$P"` | `opencode run --standalone --auto --format json -m prov/model "$P" </dev/null` | `pi --mode json --session-id ID --model prov/model "$P"` (no permission system) | `agy -p "$P" --output-format stream-json --dangerously-skip-permissions` | `gemini -p "$P" -o stream-json --approval-mode yolo` |
| Cwd | process cwd | `-C DIR` | process cwd (set `PWD` too) | process cwd | process cwd | process cwd |
| Session id | `session_id` (init + result) | `thread.started.thread_id` | `sessionID` (every event) | first line `{"type":"session","id"}` | `conversation_id` | `init.session_id` |
| Usage (per step) | `assistant.message.usage` (dedupe by `message.id`; output is placeholder) | none per step in `--json` (running total on `turn.completed`) | `step_finish.part.tokens{input,output,reasoning,cache{read,write}}`, `.cost` | `message_end.message.usage{input,output,cacheRead,cacheWrite,reasoning,cost.total}` | `step_update.usage` (UNVERIFIED populated) | none (stream-json); `-o json` has `stats.models.*.tokens` |
| Usage (total) | `result.usage` (excl. subagents), `result.modelUsage` + `total_cost_usd` (incl.) | `turn.completed.usage{input_tokens,cached_input_tokens,cache_write_input_tokens,output_tokens,reasoning_output_tokens}` (cumulative) | sum of `step_finish` | sum of `message_end` | `result.usage{input_tokens,output_tokens,thinking_tokens,cache_read_tokens,total_tokens}` | `result.stats{input_tokens,output_tokens,cached,input,total_tokens}` |
| Cost | `total_cost_usd` (estimate) | none | `step_finish.part.cost` | `usage.cost.total` | none | none |
| Tool call events | assistant `content[].type=="tool_use"{name,input}` | `item.*` `command_execution.command`, `file_change.changes[].path` | `tool_use.part{tool,state.input}` | `tool_execution_start{toolName,args}` | `step_update.tool_info{name,parameters}` | `tool_use{tool_name,parameters}` |
| Final text | `result.result` | last `item.completed` `agent_message.text` | last `text.part.text` | last assistant `message_end` text | `result.response` | concatenated assistant `message` deltas |
| Resume | `claude -p "$M" --resume ID ...` | `codex exec -C DIR -s ... resume ID --json "$M"` | `opencode run ... -s ID "$M"` | `pi --mode json --session-id ID "$M"` | `agy -p "$M" --conversation ID ...` | `gemini -p "$M" --resume ID ...` |
| Subagents off | `--disallowedTools Agent` | `-c agents.enabled=false --disable multi_agent` | deny rule `action:"subagent"` | none built in | no switch; custom agent w/o `invoke_subagent` | `agents.overrides.{codebase_investigator,cli_help,generalist}.enabled=false` |
| Ask-user off | `--disallowedTools AskUserQuestion` / `--permission-prompts none` | `-c tools.experimental_request_user_input.enabled=false` (exec rejects anyway) | deny rule `action:"question"` | none built in | tool `ask_question` (headless self-answers) | `ask_user` (auto-excluded in `-p`) |
| Turn limit | `--max-turns N` (hidden flag) | none | `agents.<id>.steps` | none | none (`--print-timeout`) | `model.maxSessionTurns` |
| Custom endpoint | Anthropic API only (`ANTHROPIC_BASE_URL`, env) | OpenAI Responses API only (`wire_api="responses"`), `config.toml` or `-c` | OpenAI-compat + Anthropic-compat providers via `OPENCODE_CONFIG_CONTENT` | OpenAI-compat/Anthropic via `$PI_CODING_AGENT_DIR/models.json` | Gemini API only | Gemini API only (`GOOGLE_GEMINI_BASE_URL`) |
| Subscription auth | `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) | copy `auth.json` to `$CODEX_HOME` | `opencode auth export/import` (sqlite store) | copy `$PI_CODING_AGENT_DIR/auth.json` | keyring; file fallback path UNVERIFIED | copy `oauth_creds.json` to `$GEMINI_CLI_HOME/.gemini/` |
| API-key auth | `ANTHROPIC_API_KEY` | `CODEX_API_KEY` | provider env vars with `--standalone` | provider env vars | `GEMINI_API_KEY` | `GEMINI_API_KEY` |
| Instruction files | CLAUDE.md, AGENTS.md fallback; `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` | AGENTS.md; `-c project_doc_max_bytes=0` | AGENTS.md; `OPENCODE_DISABLE_PROJECT_CONFIG=1` | AGENTS.md/CLAUDE.md; `--no-context-files` | AGENTS.md, GEMINI.md, `.agents/`; cannot disable | GEMINI.md; `context.fileName` |
| Exclude from diff | `.claude/` | `.codex/` (defensive) | `opencode.json*`, `.opencode/` | `.pi/` (defensive) | `.gemini/`, `.agents/`, `.agent/`, `.metadata.json` | `.gemini/` |

Cross-cutting notes:
- Custom OpenAI-compatible endpoints (Ollama/vLLM): OpenCode and Pi accept them natively. Codex needs `/v1/responses` (Ollama >= 0.13.3). Claude Code needs an Anthropic-compatible `/v1/messages` server (Ollama supports it; otherwise a proxy such as LiteLLM). agy and Gemini CLI need a Gemini-API-compatible endpoint (proxy required for Ollama/vLLM).
- Token-field semantics differ: Claude `input_tokens` and OpenCode `tokens.input` and Pi `input` EXCLUDE cache reads; Codex `input_tokens` and Gemini `input_tokens` INCLUDE cached tokens (Codex `cached_input_tokens`, Gemini `cached` are the subset). Normalize in the adapter.
- Subagent token accounting: Claude `result.usage` excludes subagents (use `modelUsage`/`total_cost_usd`); OpenCode stream omits child-session events (read sqlite `session_v2` by `parent_id`); Pi's example subagent extension spawns separate `pi` processes.
- Root-in-container: Claude's bypass mode refuses root unless `IS_SANDBOX=1`.

## Claude Code 2.1.319

Local binary: `~/.local/bin/claude -> ~/.local/share/claude/versions/2.1.319` (native Bun-compiled Mach-O; verified `ls -la`, `claude --version` -> `2.1.319 (Claude Code)`).
Sources used: `claude --help` (2.1.319), `strings` of the 2.1.319 binary, `@anthropic-ai/claude-agent-sdk@0.3.318` `sdk.d.ts` / `sdk-tools.d.ts` (bundles CC 2.1.318), code.claude.com/docs (setup, headless, env-vars, sub-agents, agent-sdk/cost-tracking), `https://claude.ai/install.sh`, npm registry, a local transcript under `~/.claude/projects` (usage object shape only).

### 1. Install (Linux, glibc + musl, amd64 + arm64)

- npm: `npm install -g @anthropic-ai/claude-code@2.1.319` — verified (`npm view`): version exists (dist-tag `next`; `latest`=2.1.318, `stable`=2.1.311 at time of check), `engines.node >=22.0.0`, optionalDependencies `@anthropic-ai/claude-code-linux-{x64,arm64}` and `-linux-{x64,arm64}-musl` @2.1.319. The npm package just links a native binary; it does not run on Node at runtime (docs/setup). Needs optional deps enabled (no `--omit=optional`).
- Native installer (pins version): `curl -fsSL https://claude.ai/install.sh | bash -s 2.1.319` — verified (script source + docs/setup). Installs to `$HOME/.local/bin/claude`; script auto-detects musl via `/lib/libc.musl-*.so.1` or `ldd /bin/ls` and picks `linux-<arch>-musl`. Requires bash + curl/wget.
- Direct binary (best for Dockerfiles, no installer, no $HOME writes) — verified HTTP 200 for all four:
  `https://downloads.claude.ai/claude-code-releases/2.1.319/{linux-x64,linux-arm64,linux-x64-musl,linux-arm64-musl}/claude`
  (checksums in `https://downloads.claude.ai/claude-code-releases/2.1.319/manifest.json` under `.platforms["<platform>"].checksum`).
  ```dockerfile
  ARG CC_VER=2.1.319
  RUN set -e; arch=$(uname -m); case $arch in x86_64) a=x64;; aarch64) a=arm64;; esac; \
      if ldd /bin/ls 2>&1 | grep -q musl || [ -e /lib/libc.musl-$(uname -m).so.1 ]; then a="$a-musl"; fi; \
      curl -fsSL -o /usr/local/bin/claude https://downloads.claude.ai/claude-code-releases/$CC_VER/linux-$a/claude; \
      chmod +x /usr/local/bin/claude
  ```
- Alpine/musl runtime deps: `apk add bash curl libgcc libstdc++ ripgrep` and set `USE_BUILTIN_RIPGREP=0` — verified (docs/setup "Alpine Linux and musl-based distributions"; ripgrep is in the community repo). Alpine 3.19+ supported.
- Set `DISABLE_AUTOUPDATER=1` (or `DISABLE_UPDATES=1`) in containers — verified (docs/env-vars).

### 2. Headless invocation

```bash
cd /workspace/repo && IS_SANDBOX=1 claude -p "$PROMPT" \
  --output-format stream-json --verbose \
  --permission-mode bypassPermissions \
  --max-turns 200 \
  --model "$MODEL"
```
- Prompt: positional arg with `-p`, or stdin (`echo "$PROMPT" | claude -p ...`; piped stdin capped at 10MB) — verified (docs/headless). `--input-format stream-json` also exists for NDJSON input.
- Working dir: no `--cwd` flag; uses process cwd (run with `cd` / `docker exec -w /workspace/repo`). `--add-dir` adds extra dirs — verified (`--help`).
- JSON: `--output-format json` (single result object) or `stream-json` (NDJSON). Docs pair `stream-json` with `--verbose` (required with `-p`; UNVERIFIED that it hard-errors without it in 2.1.319, but historically it does — always pass `--verbose`).
- Auto-approve: `--permission-mode bypassPermissions` (== `--dangerously-skip-permissions`). Since v2.1.302, `-p` runs default to Manual mode where anything needing approval is denied (docs/headless). Alternatives: `--permission-mode acceptEdits` + `--allowedTools "Bash"`; `--permission-mode auto` (classifier).
  - ROOT GOTCHA (verified in binary): bypass is refused with `--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons` when `getuid()==0` unless `IS_SANDBOX=1` (or `CLAUDE_CODE_BUBBLEWRAP` is set). In root containers export `IS_SANDBOX=1`, or run as a non-root user.
- `--permission-prompts none` (v2.1.259+): anything that would prompt is auto-denied and the human-input tools (AskUserQuestion) are removed — verified (docs/headless).
- `-p` skips the workspace trust dialog — verified (`--help`).
- Recommended extras for evals: `--no-session-persistence` only if you never resume (it disables resume); `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `DISABLE_AUTOUPDATER=1`.

### 3. JSON output schema (stream-json)

Message types (verified from `sdk.d.ts` of agent-sdk 0.3.318 ≈ CC 2.1.318, and docs/headless):
- `{"type":"system","subtype":"init","session_id","cwd","model","tools":[...],"mcp_servers":[...],"permissionMode","agents":[...],"claude_code_version",...}` — first line (unless hook/plugin events precede).
- `{"type":"assistant","message":<Anthropic BetaMessage>,"parent_tool_use_id":null|"toolu_...","session_id","uuid"}`
  - `message.id`, `message.model`, `message.content[]` blocks: `{"type":"text","text"}`, `{"type":"thinking",...}`, `{"type":"tool_use","id","name","input"}`.
  - `message.usage` (real local example): `{"input_tokens":2,"cache_creation_input_tokens":17394,"cache_read_input_tokens":26952,"output_tokens":251,"output_tokens_details":{"thinking_tokens":68},"cache_creation":{"ephemeral_1h_input_tokens":17394,"ephemeral_5m_input_tokens":0},"server_tool_use":{...},"service_tier":"standard",...}`
  - GOTCHAS (verified, docs/agent-sdk/cost-tracking): one API response is split into several `assistant` lines sharing the same `message.id` with identical usage — dedupe by `message.id`. Per-step `output_tokens` is a placeholder (value at `message_start`); take output tokens from the `result`. `parent_tool_use_id != null` marks subagent messages.
- `{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id","content","is_error"}]},"parent_tool_use_id",...}`
- `{"type":"system","subtype":"api_retry","attempt","max_retries","retry_delay_ms","error_status","error"}`; `permission_denied` system messages when denied.
- Final: `{"type":"result","subtype":"success"|"error_max_turns"|"error_during_execution"|"error_max_budget_usd"|"error_max_structured_output_retries","is_error","num_turns","result":"<final text>","stop_reason","total_cost_usd","usage":{input_tokens,cache_creation_input_tokens,cache_read_input_tokens,output_tokens,...},"modelUsage":{"<model>":{"inputTokens","outputTokens","thinkingTokens?","cacheReadInputTokens","cacheCreationInputTokens","webSearchRequests","costUSD","contextWindow","maxOutputTokens"}},"permission_denials":[{"tool_name","tool_use_id","tool_input"}],"duration_ms","duration_api_ms","session_id","uuid"}` (`result` field only on success; errors carry `errors:[...]`).
  - `usage` excludes subagent tokens; `total_cost_usd` and `modelUsage` include them → use `modelUsage` for whole-tree totals (verified, cost-tracking doc). Cost is a client-side estimate. On resume, result totals include earlier runs of the session (since v2.1.277) → take the latest result, do not sum.
- Tool names + inputs for path extraction (verified, `sdk-tools.d.ts`): `Read{file_path,offset?,limit?}`, `Edit{file_path,old_string,new_string,replace_all?}`, `Write{file_path,content}`, `NotebookEdit{notebook_path,...}`, `Glob{pattern,path?}`, `Grep{pattern,path?,glob?,...}`, `Bash{command,timeout?,run_in_background?}`, `Agent{description,prompt,subagent_type?,model?}`, `AskUserQuestion{questions:[...]}`, `TodoWrite{todos}`, `WebFetch{url,prompt}`, `WebSearch{query}`.

### 4. Resume headlessly

`claude -p "No human is available, use your best judgement and continue" --resume "$SESSION_ID" --output-format stream-json --verbose --permission-mode bypassPermissions` — verified (docs/headless; `-r, --resume [value]` in `--help`). `-c/--continue` = most recent in cwd. `--fork-session` to branch. `--session-id <uuid>` lets you pre-assign the id on the first run (verified `--help`). Session found by id from any cwd; transcript at `$CLAUDE_CONFIG_DIR/projects/<cwd-slug>/<session_id>.jsonl`.

### 5. Subagents / ask-user

- Subagent tool is `Agent` (renamed from `Task` in v2.1.63; `Task(...)` still an alias) — verified (docs/sub-agents; binary has `="Agent"&&e!=="Task"`).
- Disable all delegation: `--disallowedTools "Agent"` (or settings `{"permissions":{"deny":["Agent"]}}`) — verified (docs/sub-agents + `--help`). Belt-and-braces: `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` (removes Explore/Plan/general-purpose in `-p` mode) — verified (docs/env-vars). Also consider disallowing `Workflow` and the task-list tools only if your strategy requires it (tool names exist in `sdk-tools.d.ts`; UNVERIFIED whether enabled by default in `-p`).
- Disable ask-user: `--disallowedTools "AskUserQuestion"` or `--permission-prompts none` (removes it) — verified (docs/headless). In `dontAsk` mode it is always denied.
- Combined: `--disallowedTools "Agent,AskUserQuestion"`.
- Enable subagents ("harness-native"): default on; built-ins Explore/Plan/general-purpose; custom via `--agents '{"name":{"description":"...","prompt":"..."}}'` — verified (`--help`). Nesting depth: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` (default 3) — verified (docs/sub-agents). `CLAUDE_CODE_SUBAGENT_MODEL` sets subagent model. `--forward-subagent-text` to see subagent text in stream.
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` prevents background subagents/commands (simplifies end-of-run) — verified (docs/env-vars).

### 6. Turn limits

`--max-turns <n>` — hidden from `--help` but present in 2.1.319 binary: `"Maximum number of agentic turns in non-interactive mode. This will early exit the conversation after the specified number of turns. (only works with --print)"`; ends with result `subtype:"error_max_turns"` (verified, binary strings + sdk.d.ts). `--max-budget-usd <amount>` also available (`--help`).

### 7. Custom model endpoint (Anthropic-compatible only)

Claude Code speaks the Anthropic Messages API only; there is no OpenAI-compatible mode (UNVERIFIED as a negative, but no such option exists in `--help`/env list). Use an Anthropic-compatible server: Ollama (native `/v1/messages`) or vLLM (`/v1/messages`), or a LiteLLM proxy for OpenAI-only backends.
```bash
ANTHROPIC_BASE_URL=http://host.docker.internal:11434   # Ollama (no /v1 suffix)
ANTHROPIC_AUTH_TOKEN=ollama                            # sent as "Authorization: Bearer ..."
ANTHROPIC_API_KEY=""                                   # must be empty so it isn't preferred
ANTHROPIC_MODEL=qwen3-coder:30b                        # or --model
ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen3-coder:30b          # background/small-model calls
CLAUDE_CODE_SUBAGENT_MODEL=qwen3-coder:30b
```
Ollama values verified from docs.ollama.com/integrations/claude-code (needs >=64k context). Env var names verified (binary strings + docs/env-vars). All config is env-only, so no $HOME files needed; `--settings '<json>'` can also supply `{"env":{...}}`. For vLLM: `ANTHROPIC_BASE_URL=http://host.docker.internal:8000` (UNVERIFIED path handling; vLLM serves `/v1/messages`).

### 8. Subscription auth in a container

- On host: `claude setup-token` (requires subscription) → long-lived token; in container: `CLAUDE_CODE_OAUTH_TOKEN=<token>` — verified (`--help` setup-token; docs/env-vars: "Alternative to /login for SDK and automated environments... Takes precedence over keychain-stored credentials").
- API key alternative: `ANTHROPIC_API_KEY`.
- Do NOT use `--bare` with subscription auth: bare mode never reads OAuth ("Anthropic auth is strictly ANTHROPIC_API_KEY or apiKeyHelper") — verified (`--help`).
- `CLAUDE_CONFIG_DIR` relocates `~/.claude` (settings, sessions) — verified (docs/env-vars). Note `~/.claude.json` (global state) normally lives in $HOME; with `CLAUDE_CONFIG_DIR` it moves inside it (UNVERIFIED for 2.1.319). Onboarding dialogs don't run in `-p` mode (UNVERIFIED but standard behavior).

### 9. Files written to repo / auto-loaded instructions

- Writes to the repo: normally nothing; transcripts go to `$CLAUDE_CONFIG_DIR/projects/...`. Possible repo-local artifacts to exclude from diffs: `.claude/` (settings.local.json if permissions are persisted, worktrees under `.claude/worktrees` with `-w`), `CLAUDE.md` only if the agent writes it (UNVERIFIED that anything is created automatically in `-p`). Safe to add `.claude/` to the diff exclude list.
- Auto-loaded: `CLAUDE.md` / `.claude/CLAUDE.md` / `CLAUDE.local.md` up the tree, `~/.claude/CLAUDE.md`, auto memory, project `.claude/settings.json` hooks and `.mcp.json` (even untrusted, in `-p`) — verified (docs/headless bare-mode section). **AGENTS.md IS loaded in 2.1.319**: binary strings describe a built-in "Project instructions" feature with an `instructionFiles` option: `"claude-md-or-agents-md" (default): a project with no CLAUDE.md of its own gets its AGENTS.md files instead`, other values `claude-md`, `claude-md-and-agents-md`, `managed-only` (verified, binary strings; exact settings path for `instructionFiles` UNVERIFIED). Since CooperBench repos may ship AGENTS.md, treat it as loaded unless disabled.
- Disable: `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` ("prevent loading any CLAUDE.md memory files... including user, project, and auto memory") — verified (docs/env-vars, binary); whether it also suppresses the AGENTS.md fallback is UNVERIFIED (likely, since AGENTS.md is loaded "exactly where and how CLAUDE.md would be") — if it matters, delete/rename AGENTS.md in the container before the run. `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. `--setting-sources ""`/`user` to skip project settings; `--strict-mcp-config` to skip `.mcp.json`. `--bare` does all of this but forces API-key auth. `--safe-mode` disables customizations but keeps auth (verified `--help`).

---

## Codex CLI 0.166.0 (`codex exec`)

Local: `~/.local/bin/codex -> ~/.codex/packages/standalone/releases/0.166.0-aarch64-apple-darwin/bin/codex` (`codex-cli 0.166.0`). Sources: `codex --help`, `exec --help`, `exec resume --help`, `codex features list`, `strings` of the binary, GitHub source at tag `rust-v0.166.0` (`codex-rs/exec/src/lib.rs`, `exec_events.rs`, `event_processor_with_jsonl_output.rs`, `model-provider-info/src/lib.rs`, `agents_md.rs`, `spec_plan.rs`, cli.rs), npm registry, release assets, official docs (developers.openai.com/codex → learn.chatgpt.com), local rollouts in `~/.codex/sessions` (structure only). No model calls made.

Key gotchas:
- `wire_api = "chat"` is REMOVED in 0.166 → custom endpoints must serve `POST /v1/responses`.
- `--full-auto` no longer exists.
- `codex exec` always forces approval policy `never`; the sandbox mode is the only knob.
- `turn.completed.usage` is the RUNNING THREAD TOTAL, not per-turn.
- On resume, `-s`/`-C`/`--add-dir`/`--oss`/`-p` must come BEFORE the `resume` subcommand.
- File reads are only visible as shell commands in `--json` output.

### 1. Install
- npm: `npm i -g @openai/codex@0.166.0` — verified (`npm view`). On Linux `bin/codex.js` loads `@openai/codex@0.166.0-linux-x64` / `-linux-arm64`, which contain the `x86_64-unknown-linux-musl` / `aarch64-unknown-linux-musl` static builds (verified in tarball) → one binary works on Debian, node, rust and Alpine images. Needs Node; ~456 MB (x64) / ~409 MB (arm64) unpacked.
- No Node (verified release assets; only musl Linux builds published):
  ```dockerfile
  RUN ARCH=$(uname -m) && \
      curl -fsSL https://github.com/openai/codex/releases/download/rust-v0.166.0/codex-${ARCH}-unknown-linux-musl.tar.gz | tar xz -C /usr/local/bin && \
      mv /usr/local/bin/codex-${ARCH}-unknown-linux-musl /usr/local/bin/codex
  ```
  (file name inside the tarball UNVERIFIED — `ls` after extracting). Also published: `codex-package-<triple>.tar.gz`, `bwrap-<triple>.tar.gz`, `install.sh` (`--release VERSION`, `CODEX_INSTALL_DIR`).

### 2. Headless invocation
```bash
codex exec --json -C /workspace/repo --skip-git-repo-check -s danger-full-access \
  [-m MODEL] [-c key=value ...] [-o /tmp/last_message.txt] "PROMPT"
```
- Prompt: positional, or `-`/omitted → stdin; if both, stdin appended as a `<stdin>` block (verified `exec --help`).
- Cwd: `-C/--cd` (verified).
- JSON: `--json` → JSONL on stdout; `-o FILE` writes the final message (verified).
- Approvals: exec sets approval to `never` (verified lib.rs:595); approval requests, ask-user and dynamic tool calls are auto-rejected; MCP elicitations auto-cancelled.
- Sandbox in Docker: `-s danger-full-access` (or `--dangerously-bypass-approvals-and-sandbox`, alias `--yolo`, which also skips the git-repo check). `-s workspace-write` uses bubblewrap/landlock which likely fails in unprivileged Docker (needs user namespaces) — UNVERIFIED.
- `--approve-for-me` = `approvals_reviewer="auto_review"`, `approval_policy="on-request"`, `sandbox_mode="workspace-write"` (a model reviews requests) — not needed.
- Outside a git repo exec exits unless `--skip-git-repo-check` (or `--yolo`).

### 3. JSONL schema (verified from `exec_events.rs` / `event_processor_with_jsonl_output.rs`)
Top-level `type`: `thread.started{thread_id}`, `turn.started{}`, `turn.completed{usage}`, `turn.failed{error:{message}}`, `item.started|item.updated|item.completed{item:{id,type,...}}`, `error{message}`.

`usage`: `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens` (default 0), `output_tokens`, `reasoning_output_tokens`. Running thread total → take deltas between turns; after resume the total likely includes earlier turns (UNVERIFIED). No cost field.

| item.type | fields |
|---|---|
| `agent_message` | `text` (final answer = last one) |
| `reasoning` | `text` (summary) |
| `command_execution` | `command` (string), `aggregated_output`, `exit_code`, `status` (`in_progress`/`completed`/`failed`/`declined`) |
| `file_change` | `changes:[{path, kind: add|delete|update}]`, `status` (emitted on completion) |
| `mcp_tool_call` | `server`, `tool`, `arguments`, `result`, `error`, `status` |
| `collab_tool_call` (subagents) | `tool` (`spawn_agent`/`send_input`/`wait`/`close_agent`), `sender_thread_id`, `receiver_thread_ids`, `prompt`, `agents_states`, `status` |
| `web_search` | `id`, `query`, `action`, `results?` |
| `todo_list` | `items:[{text,completed}]` |
| `error` | `message` |

Examples (first four from official docs; `turn.completed` field names from source, numbers illustrative):
```json
{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"bash -lc ls","status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"Repo contains docs, sdk, and examples directories."}}
{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"cache_write_input_tokens":0,"output_tokens":122,"reasoning_output_tokens":0}}
```
- Read paths: no read item → parse `command_execution.command` (`sed -n`, `cat`, `rg`, ...). Edit paths: `file_change.changes[].path`. In "code mode" (JS `exec` tool calling `tools.exec_command`) the inner commands still appear as command items (verified in a local 0.162.1 rollout).
- Richer alternative — rollout file `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<thread_id>.jsonl` (internal format, stability UNVERIFIED; structure verified locally):
  - `event_msg`/`item_completed` with `item.type=="CommandExecution"`: `command` (argv array), `cwd`, `parsed_cmd:[{"type":"read","cmd","name","path"}]` → read paths directly.
  - `event_msg`/`token_count`: `info.total_token_usage` and `info.last_token_usage` (five fields + `total_tokens`), `model_context_window`, `rate_limits` → per-step usage.
  - `token_usage_record`: `{thread_id, turn_id, response_id, usage, turn_token_usage, thread_token_usage}`.
  - `response_item` `function_call`/`custom_tool_call` raw tool names seen: `exec_command`, `apply_patch`, `exec`, `write_stdin`, `update_plan`, `request_user_input`, `wait`.
- Don't use `--ephemeral` (no rollout, no resume).

### 4. Resume (verified `exec resume --help`, cli.rs)
```bash
codex exec -C /workspace/repo -s danger-full-access resume "$THREAD_ID" --json --skip-git-repo-check \
  "No human is available, use your best judgement and continue"
```
Global (position-independent) flags: `-m`, `--yolo`, `--json`, `-c`, `--skip-git-repo-check`, `--ephemeral`. Non-global (put before `resume`): `-s`, `-C`, `--add-dir`, `--oss`, `-p`. `--last` = newest session, `--all` disables cwd filtering.

### 5. Subagents / ask-user (verified config source, spec_plan.rs, `codex features list`)
- Feature `multi_agent` ON by default → tools `spawn_agent`, `send_input`, `resume_agent`, `wait`, `close_agent`. `multi_agent_v2` OFF by default (adds `followup_task`, `send_message`, `interrupt_agent`, `list_agents`; overrides `agents.enabled`).
- Disable: `-c agents.enabled=false --disable multi_agent` (keep `multi_agent_v2` off).
- Enable: default; tune `-c agents.max_threads=N`, `agents.max_depth`, `agents.default_subagent_model`; v2 via `--enable multi_agent_v2`.
- Ask-user tool `request_user_input`: registered but only usable in Plan mode (Default mode needs feature `default_mode_request_user_input`, off); exec rejects it anyway ("not supported in exec mode"). Belt-and-braces: `-c tools.experimental_request_user_input.enabled=false` (also drops `request_user_input_async`).
- `update_plan` off unless `tools.update_plan.enabled=true`. Web search: `-c web_search="disabled"` (value UNVERIFIED).

### 6. Turn limits
None in 0.166 (no config keys/strings). `token_budget` / `rollout_budget` exist but are under-development and off. Use an external wall-clock timeout.

### 7. Custom endpoint (verified `model-provider-info/src/lib.rs`)
- Only `wire_api = "responses"` accepted. Ollama supports `/v1/responses` from v0.13.3 (non-stateful) — verified (Ollama docs). vLLM `/v1/responses`: UNVERIFIED (recent vLLM has it; check your version).
- Built-in `ollama`/`lmstudio` providers (cannot be overridden) read `CODEX_OSS_BASE_URL` / `CODEX_OSS_PORT`:
  ```bash
  CODEX_OSS_BASE_URL=http://host.docker.internal:11434/v1 codex exec --oss --local-provider ollama -m qwen3-coder:30b --json ...
  ```
- Custom provider in `$CODEX_HOME/config.toml`:
  ```toml
  model_provider = "vllm"
  model = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
  model_context_window = 131072          # probably needed for unknown models (UNVERIFIED)
  [model_providers.vllm]
  name = "vLLM"
  base_url = "http://host.docker.internal:8000/v1"
  wire_api = "responses"
  env_key = "VLLM_API_KEY"               # optional; alternatives: experimental_bearer_token, http_headers
  ```
- No-file form (`-c` syntax verified; nested provider via `-c` UNVERIFIED):
  `-c model_provider=vllm -c model_providers.vllm.name=vllm -c 'model_providers.vllm.base_url="http://host.docker.internal:8000/v1"' -c model_providers.vllm.wire_api=responses -m <model>`
- Top-level `openai_base_url` redirects the built-in OpenAI provider.
- Avoid $HOME: `CODEX_HOME=<dir>` (must exist). `-p NAME` layers `$CODEX_HOME/NAME.config.toml`. `--ignore-user-config` skips config.toml but still reads auth from `CODEX_HOME`.

### 8. Auth in a container
- API key: `CODEX_API_KEY=<key> codex exec ...` — verified (docs).
- ChatGPT subscription: copy host `~/.codex/auth.json` into `$CODEX_HOME/auth.json` (docs endorse this for headless machines); keep it writable (token refresh); set `-c cli_auth_credentials_store=file` so it doesn't look for a keyring. Shape: `{auth_mode, OPENAI_API_KEY, tokens:{id_token,access_token,refresh_token,account_id}, last_refresh}`. Parallel containers refreshing one shared file may race (UNVERIFIED) → give each container its own copy.
- Others: `codex login --device-auth` (beta), `printenv CODEX_ACCESS_TOKEN | codex login --with-access-token`.

### 9. Files written / instructions
- Loads `AGENTS.override.md`, `AGENTS.md`, plus `project_doc_fallback_filenames`, from project root down to cwd (32 KiB cap), and a user-level file in `$CODEX_HOME` (exact name UNVERIFIED; historically `AGENTS.md`). Disable: `-c project_doc_max_bytes=0` (verified agents_md.rs stops immediately); fresh `CODEX_HOME` avoids the user file.
- State in `$CODEX_HOME` (sessions, sqlite, logs, shell_snapshots, history.jsonl). Nothing known written into the repo (UNVERIFIED) — exclude `.codex/` from diffs defensively. `--ignore-rules` skips `.rules` exec-policy files.

---

## OpenCode v2.2.4

Local: `~/.opencode/bin/opencode` (`opencode v2.2.4`, compiled static binary). Sources: `--help`, `strings`/embedded JS of the binary, npm + GitHub metadata, v2 docs at opencode.ai/v2/docs, local sqlite DB (read-only), and real `opencode run --format json` transcripts from earlier runs under `/Users/vishesh/College/4-1/ASE/assignment-1/local_kit/runs/opencode_glm_5_3_flash_free/*/T1_room_booking/r1/transcript.jsonl`. No model calls made here.

Key points:
- v2 is a DIFFERENT package: `@opencode/cli` (not `opencode-ai`, which stops at 1.19.5). `https://opencode.ai/install` refuses 2.x.
- Config format changed from v1: keys `providers`, `agents`, an ordered `permissions` array, `steps`. Tools renamed: `bash`->`shell`, `task`->`subagent`, `apply_patch`->`patch`. CLAUDE.md is no longer read; only AGENTS.md.
- Use `--standalone`, otherwise the CLI talks to a shared background daemon that does not see your env vars.
- Note: the binary also contains hidden aliases `--yolo` and `--dangerously-skip-permissions` for `--auto`; we use the documented `--auto` only (and it was NOT executed against a model in this research).

### 1. Install (Linux)
- Recommended (no Node): per-platform npm tarball containing one static binary at `package/bin/opencode` (verified `npm view @opencode/cli@2.2.4 optionalDependencies`, `tar tz`):
  ```dockerfile
  ARG OC_VER=2.2.4
  RUN set -e; case "$(uname -m)" in x86_64) a=x64;; aarch64|arm64) a=arm64;; esac; \
      l=""; if [ -f /etc/alpine-release ] || (ldd --version 2>&1 | grep -qi musl); then l="-musl"; fi; \
      curl -fsSL "https://registry.npmjs.org/@opencode/cli-linux-${a}${l}/-/cli-linux-${a}${l}-${OC_VER}.tgz" \
        | tar xz -C /tmp && install -m755 /tmp/package/bin/opencode /usr/local/bin/opencode && rm -rf /tmp/package
  ```
  Platform packages @2.2.4 (verified): `@opencode/cli-linux-{x64,arm64}`, `-linux-{x64,arm64}-musl`, `-linux-x64-baseline`, `-linux-x64-baseline-musl` (baseline = CPUs without AVX2).
- Alternatives: `npm i -g @opencode/cli@2.2.4` (postinstall picks musl/AVX2 binary; needs scripts + network; verified `postinstall.mjs`). `curl -fsSL https://opencode.ai/v2/install | bash -s -- --version 2.2.4` (installs to `$HOME/.opencode/bin`; needs bash). GitHub assets `https://github.com/anomalyco/opencode/releases/download/v2.2.4/opencode-linux-{arm64,x64}[-baseline][-musl].tar.gz` (verified `gh release view`, URL 206).
- UNVERIFIED: Alpine musl binary may need `apk add libstdc++ libgcc`. `git` required for snapshots (docs).

### 2. Headless invocation
```bash
cd /workspace/repo && PWD=/workspace/repo \
OPENCODE_CONFIG_CONTENT="$(cat /opt/oc/config.json)" \
opencode run --standalone --auto --format json -m <provider>/<model>[#variant] [--agent build] "<prompt>" </dev/null
```
- Prompt: positional; if stdin is not a TTY it is also read and appended (verified binary) -> use `</dev/null` or pipe.
- Cwd: `run` has no dir flag; uses `process.env.PWD ?? process.cwd()` (PWD wins) -> set both (verified binary). The top-level `opencode [directory]` arg only applies to the TUI.
- `--format json` -> one JSON object per line (verified).
- `--standalone`: private in-process server; without it the CLI uses a shared daemon that doesn't see the client's env (provider keys, `OPENCODE_CONFIG_CONTENT`) (verified help + docs).
- Auto-approve: `--auto` = "Auto-approve permissions that are not explicitly denied" (verified `run --help`). Without it `run` auto-rejects every "ask" ("This non-interactive run cannot ask the user for permission, so the request was rejected. Continue without this action."). Default policy already allows everything except `*.env` reads (permissions docs).
- Exit codes: 1 on step/execution error, 130 on SIGINT. No final "result" event; process just exits (verified).

### 3. JSON event schema (`--format json`)
- Envelope: `{"type":<t>,"timestamp":<ms>,"sessionID":"ses_...", ...}`. Types: `step_start`, `text`, `reasoning` (only with `--thinking`), `tool_use`, `step_finish`, `error` (verified emitter code + real transcripts).
- `step_finish.part`: `{id,sessionID,messageID,type:"step-finish",reason,snapshot,cost,tokens:{input,output,reasoning,cache:{read,write}}}`. `tokens.input` = NON-cached input; `output` excludes reasoning; `cost` USD from catalog prices (0 for local/free). No total event -> SUM `step_finish`. Real line:
  ```json
  {"type":"step_finish","timestamp":1792346299595,"sessionID":"ses_eafd5ec7affeLAasZ6WVssOv7F","part":{"id":"prt_...","sessionID":"ses_...","messageID":"msg_...","type":"step-finish","reason":"tool-calls","snapshot":"483c39b2...","cost":0,"tokens":{"input":8812,"output":82,"reasoning":0,"cache":{"read":0,"write":0}}}}
  ```
- `tool_use.part`: `{partID,sessionID,messageID,type:"tool",id,tool,state:{status:"completed"|"error",input:{...},output|error,title,metadata:{...},time:{start,end}}}`. Example: `{"type":"tool_use",...,"part":{...,"tool":"read","state":{"status":"completed","input":{"path":"/abs/path/problem.md"},"output":"..."}}}`.
- Tool names/inputs (v2; verified binary + real data): `read{path,offset,limit}`, `write{path,content}`, `edit{path,oldString,newString,replaceAll}`, `patch{patchText}` (`*** Add/Update/Delete File` sections; GPT models only), `shell{command,workdir,timeout,background}`, `glob{pattern,path}`, `grep{pattern,path,include}`, `webfetch{url}`, `websearch{query}`, `subagent{agent,description,prompt,model,background}`, `execute` (Code Mode JS; nested tool calls hidden inside it), `question`, `skill{id}`, `todowrite` (experimental). `input.path` usually absolute.
- `text.part`: `{id,sessionID,messageID,type:"text",text,time:{start,end}}`; final answer = last `text` event.
- `error`: `{"type":"error",...,"error":{type?,message}}`.
- SUBAGENT CAVEAT (verified binary): events whose `sessionID` is not the main session are skipped, so child-session usage is NOT in the stream. Read from the DB: `sqlite3 "$(opencode debug paths db)" "select id,parent_id,agent,cost,tokens_input,tokens_output,tokens_reasoning,tokens_cache_read,tokens_cache_write from session_v2 where id=? or parent_id=?"`. Whether parent totals already include children: UNVERIFIED -> sum per session and cross-check.

### 4. Resume
`opencode run --standalone --auto --format json -s <sessionID> "No human is available, use your best judgement and continue" </dev/null` — `-s`: "Session ID to continue, or to create if it does not exist" (verified help). Also `-c/--continue` (last session for dir) and `--fork`. Sessions persist in sqlite `~/.local/share/opencode/opencode.db` (`OPENCODE_DB` or `XDG_DATA_HOME` moves it); resume across standalone runs needs that DB to persist (inferred, not tested). Take `sessionID` from the first event (custom ids probably must match `ses_[0-9A-Za-z]{26}`, UNVERIFIED).

### 5. Subagents / question tool
- A tool vanishes from the model's list when the LAST matching permission rule for its action is `resource:"*", effect:"deny"` (verified).
- Disable subagents: `{"action":"subagent","resource":"*","effect":"deny"}`. Disable questions: `{"action":"question","resource":"*","effect":"deny"}`. Put both at top level AND under `agents.build.permissions` (built-in `build` agent re-allows questions after defaults; agent rules apply last).
- If question stays on, `run` auto-cancels it with "Continue without an answer; make reasonable assumptions". A plain-text "should I...?" stop still needs the resume step.
- Also deny `execute` (Code Mode) so tool calls aren't hidden in JS: `{"action":"execute","resource":"*","effect":"deny"}` (whether Code Mode is on by default UNVERIFIED).
- Enable (harness-native): default on. Built-in subagents `general` (can't spawn) and `explore` (read-only); add via `agents.<id>` with `"mode":"subagent"` or `.opencode/agents/<id>.md`; nesting `experimental.subagent_depth` (default 1).

### 6. Step limit
`agents.<id>.steps: <int>` (e.g. `{"agents":{"build":{"steps":50}}}`; v1 `maxSteps` maps here). No CLI flag. On the final step tools are removed and the model is told to summarize; new user input resets the count (verified binary schema + docs).

### 7. Custom endpoint
- Pass via `OPENCODE_CONFIG_CONTENT` (inline JSON/JSONC). Merge order low->high (verified loader): global `~/.config/opencode/opencode.json(c)` -> `OPENCODE_CONFIG` (file path) -> project `opencode.json(c)` -> project `.opencode/opencode.json(c)` -> `OPENCODE_CONFIG_CONTENT` -> managed `/etc/opencode`. So CONTENT overrides repo-shipped config; `OPENCODE_CONFIG` does not. `OPENCODE_CONFIG_DIR` moves the global dir. `{env:VAR}` and `{file:path}` substitution supported.
- Built-in local providers (docs): `ollama` (default 127.0.0.1:11434, auto-discovers models; baseURL must include `/v1`), `vllm` (127.0.0.1:8000/v1), `lmstudio`:
  ```json
  {"$schema":"https://opencode.ai/config.json",
   "model":"ollama/qwen3:8b",
   "providers":{"ollama":{"settings":{"baseURL":"http://host.docker.internal:11434/v1"}},
                "vllm":{"settings":{"baseURL":"http://host.docker.internal:8000/v1"}}},
   "snapshots":false,
   "permissions":[{"action":"*","resource":"*","effect":"allow"},
                  {"action":"subagent","resource":"*","effect":"deny"},
                  {"action":"question","resource":"*","effect":"deny"},
                  {"action":"execute","resource":"*","effect":"deny"}],
   "agents":{"build":{"steps":100,"permissions":[{"action":"subagent","resource":"*","effect":"deny"},{"action":"question","resource":"*","effect":"deny"}]}}}
  ```
- Generic OpenAI-compatible (docs): `"providers":{"local":{"name":"Local","env":["LOCAL_API_KEY"],"package":"@opencode/ai/providers/openai-compatible","settings":{"baseURL":"http://host.docker.internal:8000/v1","apiKey":"{env:LOCAL_API_KEY}"},"models":{"qwen3-coder":{"modelID":"Qwen/Qwen3-Coder-30B-A3B-Instruct","limit":{"context":131072,"output":16384}}}}}`; select `-m local/qwen3-coder`. Per-model `cost:{input,output,cache:{read,write}}` (per 1M) makes `cost` non-zero.
- Anthropic-compatible: `"package":"@opencode/ai/providers/anthropic-compatible"` or override `providers.anthropic.settings.baseURL` (docs).
- Offline: `OPENCODE_DISABLE_MODELS_FETCH=1`, `OPENCODE_DISABLE_AUTOUPDATE=1` (verified binary).

### 8. Auth
- Credentials live in the server's sqlite DB, not auth.json (legacy `<data>/auth.json` imported once on migration) (docs; `credential`/`account` tables exist).
- API keys: provider env var on the `--standalone` process, e.g. `ANTHROPIC_API_KEY=... opencode run --standalone ...` (docs). Other names follow each provider's `env` list (UNVERIFIED specifics). `OPENCODE_API_KEY` = Zen/Go.
- ChatGPT subscription: host `opencode auth export openai > oc-creds.json` (contains secrets), container `opencode auth import oc-creds.json` (or stdin). Commands verified from help; token refresh after import UNVERIFIED. Claude subscription: not offered in v2 docs (UNVERIFIED).

### 9. Files / instructions
- No repo writes observed in prior real runs. Snapshots live in `~/.local/share/opencode/snapshot/<id>` (outside repo); disable with `"snapshots": false`. `plan` agent writes `~/.opencode/plan`; logs `~/.local/share/opencode/log`.
- Exclude from diff: `opencode.json(c)`, `.opencode/`, `AGENTS.md` if your setup adds them.
- Instructions: only `AGENTS.md` (global `~/.config/opencode/AGENTS.md`, ancestors up to project root, nested as read); no CLAUDE.md fallback. Disable: `OPENCODE_DISABLE_PROJECT_CONFIG=1` (alias `OPENCODE_CONFIG_PROJECT_DISABLE`; also skips project config files). `OPENCODE_DISABLE_CLAUDE_CODE=1` / `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` for Claude-compat skills. Deny skills: `{"action":"skill","resource":"*","effect":"deny"}`. Env names verified in binary.

---

## Pi (pi-coding-agent) 0.84.4

Local: `/opt/homebrew/bin/pi -> /opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js`. Below, PKG = that package dir, AI = `PKG/node_modules/@earendil-works/pi-ai/dist`. All facts from files on disk / `pi --help` / `npm view`; Pi was not run against a model.

Key adapter gotchas:
- No permission system at all → no auto-approve flag needed.
- `--mode json` exits 0 even on errors → detect failure via `stopReason`/`errorMessage` on the last assistant `message_end`.
- No total-usage event → sum per-step `usage`.
- No turn limit → external timeout or tiny extension.

### 1. Install
- `npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.4` — verified `npm view` (0.84.4 published; `latest` is now 1.5.0, `legacy-node20` 0.74.2 → MUST pin). `--ignore-scripts` is the documented flag (PKG/README.md:66, docs/quickstart.md:10).
- Alternative: `curl -fsSL https://pi.dev/install.sh | sh` (wraps global npm install; docs only, README.md:74).
- Node: `engines.node >=22.19.0` — verified (PKG/package.json, npm). python-slim and golang-alpine images lack Node: `COPY --from=node:22-bookworm-slim /usr/local/ /usr/local/` (glibc) or from `node:22-alpine` (musl) — UNVERIFIED pattern. node:22 image fine if ≥22.19 (UNVERIFIED per tag). Alpine `apk nodejs` may be < 22.19 (UNVERIFIED).
- Native deps: pure JS; only optional native dep `@mariozechner/clipboard@0.3.9` (linux x64/arm64 gnu+musl builds) — verified. `@silvia-odwyer/photon-node` is WASM.
- Shell: bash tool tries `/bin/bash`, `bash` on PATH, then `sh` (verified PKG/dist/utils/shell.js:93-95) → `apk add bash` on Alpine.
- musl gotcha: `grep`/`find` tools (off by default) auto-download rg/fd from GitHub into `$PI_CODING_AGENT_DIR/bin`; fd download is always `-unknown-linux-gnu`, rg gnu on arm64 → broken on musl (verified PKG/dist/utils/tools-manager.js:18-56). Pi prefers system `fd`/`fdfind`/`rg` → `apk add ripgrep fd` / `apt-get install ripgrep fd-find`.
- Official Dockerfile (docs/containerization.md): `FROM node:24-bookworm-slim`; `apt-get install bash ca-certificates git ripgrep`; `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`.

### 2. Headless invocation
```bash
cd /workspace/repo && PI_OFFLINE=1 PI_CODING_AGENT_DIR=/opt/pi-agent \
  pi --mode json --session-id "$SID" --model local/qwen2.5-coder:7b \
     --no-context-files --no-skills --no-extensions --no-prompt-templates -na \
     --tools read,bash,edit,write,grep,find,ls "$PROMPT"
```
- `--mode json` alone = single-shot JSON mode; `-p` not required, harmless (verified PKG/dist/main.js:79-90).
- Prompt: positional; piped stdin is also read and prepended when not a TTY (verified main.js:47-64). Use `--` before prompts starting with `-`.
- Working dir: no flag; process cwd (verified PKG/dist/cli/args.js).
- Auto-approve: not applicable; "runs with all permissions by default", no permission popups (verified docs/containerization.md:3, docs/usage.md:309).
- Default tools `read,bash,edit,write`; `grep,find,ls` off by default (verified `--help`, agent-session.d.ts:125).
- `--thinking off|minimal|low|medium|high|xhigh|max` (verified `--help`).
- `PI_OFFLINE=1`/`--offline` disables update checks/telemetry/catalog refresh; `PI_TELEMETRY=0` (verified docs/environment-variables.md).

### 3. JSON output schema (`--mode json`, JSONL on stdout)
Verified from docs/json.md, docs/rpc.md, AI/types.d.ts, PKG/dist/core/agent-session.d.ts, print-mode.js.
- First line (session header): `{"type":"session","version":3,"id":"<sessionId>","timestamp":"...","cwd":"/workspace/repo"}` — session id = `.id` (also exported to tool shells as `PI_SESSION_ID`).
- Events: `agent_start`, `agent_end{messages,willRetry}`, `agent_settled`, `turn_start`, `turn_end{message,toolResults}`, `message_start`, `message_update{usage,assistantMessageEvent}` (deltas: `text_start|text_delta|text_end|toolcall_start|...`), `message_end{message}`, `tool_execution_start{toolCallId,toolName,args}`, `tool_execution_update{...,partialResult}`, `tool_execution_end{toolCallId,toolName,result,isError}`, `queue_update`, `compaction_start/_end`, `auto_retry_start/_end`, `entry_appended`, `session_info_changed`, `thinking_level_changed`.
- Assistant message (`message_end.message` with `role:"assistant"`): `role, content[], api, provider, model, responseModel?, responseId?, usage, stopReason, errorMessage?, timestamp`; content items `{type:"text",text}`, `{type:"thinking",...}`, `{type:"toolCall",id,name,arguments}`; `stopReason ∈ stop|length|toolUse|error|aborted|pending|deferred`.
- Per-step usage: `{input, output, cacheRead, cacheWrite, cacheWrite1h?, reasoning?, totalTokens, cost:{input,output,cacheRead,cacheWrite,total}}`.
  - `input` EXCLUDES cache tokens (OpenAI-compat: `input = prompt_tokens - cached_tokens - cache_write_tokens`; verified AI/api/openai-completions.js:1176-1202, openai-responses-shared.js:441-450).
  - `reasoning` optional, subset of `output`. `cost.total` USD from model cost table (custom models default 0).
  - Totals: sum `usage` over all `message_end` with `message.role=="assistant"`. `message_update.usage` is cumulative only for the in-flight message.
- Tool args (verified PKG/dist/core/tools/*.js; paths relative to cwd or absolute): `read{path,offset?,limit?}`, `write{path,content}`, `edit{path,edits:[{oldText,newText}]}`, `bash{command,timeout?}`, `grep{pattern,path?,glob?,ignoreCase?,literal?,context?,limit?}`, `find{pattern,path?,limit?}`, `ls{path?,limit?}`.
- Final text: text blocks of last assistant `message_end` (or last of `agent_end.messages`).
- Example lines (adapted from docs, not captured):
  ```json
  {"type":"tool_execution_start","toolCallId":"call_abc123","toolName":"bash","args":{"command":"ls -la"}}
  {"type":"tool_execution_end","toolCallId":"call_abc123","toolName":"bash","result":{"content":[{"type":"text","text":"total 48\n..."}],"details":{}},"isError":false}
  {"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"Done."}],"provider":"local","model":"qwen2.5-coder:7b","usage":{"input":100,"output":12,"cacheRead":0,"cacheWrite":0,"totalTokens":112,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}},"stopReason":"stop"}}
  ```

### 4. Resume headlessly
- `pi --mode json --session-id "$SID" "No human is available, use your best judgement and continue"` — verified (PKG/dist/main.js:237-257, 337-344; session-manager.js:15). `--session-id` opens the existing project session with that exact id or creates it (warning on stderr) → the adapter can choose the id (e.g. uuid) on the first run. Valid ids: `^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$`. Not combinable with `--session`, `-c`, `-r`.
- `pi --mode json -c "msg"` continues the most recent session for the cwd.
- Avoid `--session <path|partial>` headless: cross-project match triggers an interactive "Fork?" confirm (main.js:301-316).
- Same cwd + session dir required (lookup is per cwd).

### 5. Subagents / ask-user
- None built in: docs say Pi "intentionally does not include built-in MCP, sub-agents, permission popups, plan mode, to-dos" (verified docs/usage.md:309, README.md:501); core tools dir only has read, bash, edit, write, grep, find, ls, powershell.
- `ask_question` appears only as a help-text example (`pi --exclude-tools ask_question`, args.js:372); no bundled code defines it. Example extensions `examples/extensions/question.ts` (tool `question`) and `questionnaire.ts` add ask-user tools only if installed.
- Defensive: `--no-extensions` (`-ne`), `--no-skills` (`-ns`), `--exclude-tools question,ask_question,subagent`.
- Enable subagents: bundled example extension `PKG/examples/extensions/subagent/` registers tool `subagent` (verified index.ts:473), spawns child `pi --mode json -p --no-session` processes (index.ts:300); agent defs in `agents/*.md` (scout, planner, reviewer, worker). Load via `-e PKG/examples/extensions/subagent/index.ts` (UNVERIFIED that `-e` alone suffices; README symlinks `index.ts`, `agents.ts`, `agents/*.md` into `~/.pi/agent/extensions/subagent/` — copy into `$PI_CODING_AGENT_DIR/extensions/subagent/` equivalent, UNVERIFIED). Subagent token usage probably not in parent stream except inside tool-result details (UNVERIFIED) → for metrics, also parse child session output if possible.

### 6. Step/turn limits
- None built in (no maxTurns/maxSteps symbols in pi-agent-core/core; verified grep). Only `retry.maxRetries` (default 3) and compaction settings (docs/settings.md:114-165).
- Workaround: external timeout, or extension loaded with `-e /path/limit.ts` (UNVERIFIED, not run; `turn_end` and `ctx.abort()` documented docs/extensions.md:610, :1044):
  ```ts
  export default function (pi) { let n = 0; pi.on("turn_end", async (_e, ctx) => { if (++n >= 200) ctx.abort(); }); }
  ```

### 7. Custom model endpoint
- File: `$PI_CODING_AGENT_DIR/models.json` (default `~/.pi/agent/models.json`; verified PKG/dist/config.js:405-437). `PI_CODING_AGENT_DIR` relocates the whole config dir (models.json, auth.json, settings.json, sessions/, bin/, extensions) → no $HOME needed. Sessions separately via `PI_CODING_AGENT_SESSION_DIR`/`--session-dir`. No CLI flag for a models.json path; `--api-key` overrides the key.
- OpenAI-compatible (Ollama/vLLM) — verified docs/models.md:
  ```json
  {
    "providers": {
      "local": {
        "baseUrl": "http://host.docker.internal:11434/v1",
        "api": "openai-completions",
        "apiKey": "dummy",
        "compat": { "supportsDeveloperRole": false, "supportsReasoningEffort": false },
        "models": [ { "id": "qwen2.5-coder:7b", "contextWindow": 32768, "maxTokens": 8192, "reasoning": false } ]
      }
    }
  }
  ```
  Select with `--model local/qwen2.5-coder:7b` (or `--provider local --model ...`). `apiKey` must be non-empty or the model is marked unavailable; supports `"$ENV_VAR"` and `"!shell cmd"`. Other `api` values: `openai-responses`, `anthropic-messages`, `google-generative-ai`. Model fields: `id` (req), `name`, `api`, `reasoning`, `input`, `contextWindow` (default 128000), `maxTokens` (default 16384), `cost{input,output,cacheRead,cacheWrite}` per 1M tokens, `samplingParams`, `compat`.
- Anthropic-compatible: same shape with `"api":"anthropic-messages"`, or override built-in provider URL: `{"providers":{"anthropic":{"baseUrl":"http://host:port/v1"}}}` (verified docs/models.md "Overriding Built-in Providers").

### 8. Auth in a container
- Resolution order: `--api-key` → auth.json → env var → models.json key (verified docs/providers.md).
- Env keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_OAUTH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`, etc. (verified `--help`). Whether a `claude setup-token` token works as `ANTHROPIC_OAUTH_TOKEN`: UNVERIFIED.
- Subscription OAuth: `/login` is interactive-only; stores tokens in `$PI_CODING_AGENT_DIR/auth.json` (0600, auto-refreshed) (verified docs/providers.md:15-26). Provider ids `openai-codex` (ChatGPT Plus/Pro), `anthropic` (Claude Pro/Max), `github-copilot` (verified AI/oauth.js). Local auth.json structure: `{"openai-codex":{"type":"oauth","access","refresh","expires","accountId"},"openai":{"type":"api_key","key"}}` (structure only).
- Container: log in on host, copy auth.json into the container's `$PI_CODING_AGENT_DIR`, mount writable (refresh rewrites it). Refresh-token rotation in the container may invalidate the host copy (UNVERIFIED).
- Note: Claude Pro/Max via Pi bills "extra usage" per token, not plan limits (docs/providers.md:35).
- Check auth without a model call: `pi auth check --provider openai-codex [--no-refresh]` (verified `pi auth --help`).

### 9. Files written / context files
- Sessions: `$PI_CODING_AGENT_DIR/sessions/--<cwd with / replaced by ->--/<timestamp>_<uuid>.jsonl` (verified docs/session-format.md; session-manager.js:245). `--no-session` = ephemeral (breaks resume).
- Repo writes: none by default per docs; `.pi/` only created by `pi install -l` (docs, not observed). Exclude `.pi/` from diffs anyway.
- Agent dir writes: `pi-debug.log`, `models-store.json`, `trust.json`, `bin/`.
- Auto-loaded context: `~/.pi/agent/AGENTS.md` plus `AGENTS.md` or `CLAUDE.md` from cwd and every parent; `AGENTS.override.md` replaces in its dir; loaded regardless of trust (verified docs/usage.md:99-109, docs/security.md:27). Disable: `--no-context-files` / `-nc`.
- Project-local `.pi/settings.json`, `.pi/extensions|skills|prompts|themes`, `.pi/SYSTEM.md`, `.pi/APPEND_SYSTEM.md` load only if trusted; headless with default `defaultProjectTrust:"ask"` ignores them; `--no-approve`/`-na` forces ignoring (verified docs/security.md:29).

---

## Antigravity CLI (`agy`) 1.5.1

Local: `~/.local/bin/agy` (~200 MB binary). Sources: `agy --help`, official `install.sh` (downloaded, not run) and release manifests, settings schema `https://antigravity.google/schemas/v1/settings.json`, docs pages `/docs/cli/reference`, `/docs/cli/headless`, `/docs/install`, `/docs/settings`, `/docs/subagents`, `/docs/rules`, strings/changelog embedded in the binary. No model calls made. Caution: facts sourced only from the embedded changelog may describe features newer than 1.5.1 (e.g. `agy agents --output-format json` fails in 1.5.1 with "flags provided but not defined").

### 1. Install (Linux)
- Linux builds exist: glibc + musl, amd64 + arm64 (verified install.sh + manifests). Script detects musl via `/lib/libc.musl-{x86_64,aarch64}.so.1` or `ldd /bin/ls | grep musl`; fetches `https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/<platform>.json` -> `{version,url,sha512}`; platform keys `linux_amd64`, `linux_arm64`, `linux_amd64_musl`, `linux_arm64_musl`; verifies sha512, extracts member `antigravity` to `<dir>/agy`, runs `agy install`.
- Version 1.5.1 CANNOT be pinned via the script: manifests currently serve 1.5.2 (`https://storage.googleapis.com/antigravity-public/antigravity-cli/1.5.2-4951595792859136/{linux-x64,linux-arm,linux-x64-musl,linux-arm-musl}/cli_linux_{x64,arm64,x64_musl,arm64_musl}.tar.gz`); `/manifests/1.5.1/...` 404; bucket listing 403. The 1.5.1 build-id URL is UNVERIFIED. It self-updates in the background and no setting to stop that was found -> for reproducibility archive the tarball + sha512 yourself.
- Dockerfile: `RUN curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin` (needs bash + curl/wget; Alpine: `apk add bash curl`).

### 2. Headless
```bash
cd /workspace/repo && agy -p "$P" --output-format stream-json --dangerously-skip-permissions \
  --model M [--agent NAME] [--print-timeout 60m] [--settings '<json>|file']
```
- `-p/--print/--prompt`; `--output-format text|json|stream-json` (verified help + docs). With `-p` stdin is not read (changelog). Multi-turn in one process: `--input-format stream-json`, one NDJSON line per turn `{"event":"user","message":{"content":"..."}}`; requires `--output-format stream-json`; ignores `-p` (docs).
- No cwd flag (process cwd; `init.cwd` reports it). `--add-dir` adds dirs.
- Auto-approve: `--dangerously-skip-permissions` (init `permission_mode` = `always-proceed`) (docs). Alternatives `--mode accept-edits|auto|plan`; settings `toolPermission:"always-proceed"`, `agentMode:"accept-edits"`. Without auto-approve, headless soft-denies tools needing approval (exit 0 with stderr notice). Plan review auto-approved headless; setting `artifactReviewPolicy:"always-proceed"`.
- `--print-timeout` default 0 (none); on expiry exit code 3, `finished_reason:"print_timeout"`.

### 3. JSON output (stream-json; discriminator key is `event`, not `type`) — verified headless docs
- `init` (once): `cwd`, `tools[]`, `permission_mode`, plus `model`, `agent`, `json_schema` when set.
- `step_update` (per step / text delta): `conversation_id`, `step_index`, `state` (ACTIVE|DONE), `text_delta`, `tool_name`, `duration_seconds`, `usage`, `step_type` (user_input|agent_response|tool|checkpoint), `tool_info{name,parameters,output,error{type,message}}`, `subagent_info{type_name,role,conversation_id,log_uri,workspace_uris}`.
- `result` (once; same shape as `--output-format json`): `conversation_id`, `status` (SUCCESS|ERROR|CANCELED|INTERRUPTED|INVALID|WAITING|RUNNING), `response` (final text), `error`, `duration_seconds`, `num_turns`, `usage`, `structured_output` (with `--json-schema`), `finished_reason` (early end only; changelog).
- `usage`: `input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `total_tokens`. No cost. Cache-write field: UNVERIFIED.
- Tool names (UNVERIFIED, from binary strings; confirm with `init.tools`): `view_file`, `write_to_file`, `replace_file_content`, `multi_replace_file_content`, `list_dir`, `find_by_name`, `grep_search`, `codebase_search`, `run_command`, `search_web`, `read_url_content`, `invoke_subagent`, `manage_subagents`, `define_subagent`, `send_message`, `ask_question`, `notify_user`, `task_boundary`, `generate_image`, `ask_permission`. Parameter key names UNVERIFIED -> parse `parameters` generically.
- Shapes (built from documented fields, not captured):
  ```json
  {"event":"init","cwd":"/workspace/repo","tools":["..."],"permission_mode":"always-proceed","model":"..."}
  {"event":"step_update","conversation_id":"<uuid>","step_index":3,"state":"DONE","step_type":"tool","tool_name":"view_file","tool_info":{"name":"view_file","parameters":{},"output":"..."}}
  {"event":"result","conversation_id":"<uuid>","status":"SUCCESS","response":"...","num_turns":7,"duration_seconds":81.2,"usage":{"input_tokens":0,"output_tokens":0,"thinking_tokens":0,"cache_read_tokens":0,"total_tokens":0}}
  ```

### 4. Resume
`agy -p "$MSG" --conversation <conversation_id> --output-format stream-json --dangerously-skip-permissions`; `-c/--continue` = most recent. On resume in print mode only the new response is printed (changelog). Alternative: keep one `--input-format stream-json` process and write another line (usage and `num_turns` then cumulative).

### 5. Subagents / ask-user
- Built-in subagents (docs): `research`, `self`, `browser` (only via `/browser`), invoked through tool `invoke_subagent`.
- No global switch to disable (no flag, no schema key). Workaround: custom main agent file `~/.gemini/config/agents/nosub.md` (NOT in repo `.agents/agents/`, would pollute the diff) with frontmatter `name`, `description`, and a `tools:` allowlist omitting `invoke_subagent`, `define_subagent`, `manage_subagents`, `send_message`, `ask_question`; run `--agent nosub`. Other frontmatter: `subagent:false`, `mainAgent`, `model` (inherit|flash|pro), `commandExecutionPolicy` (off|auto|eager|sandbox). Docs warn a misspelled tool name can hang the agent; exact names UNVERIFIED. Unknown `--agent` exits 1 in `-p`.
- Enable: default on; an agent whose `tools` includes `invoke_subagent` gets the subagent roster in its prompt.
- Ask-user tool `ask_question`: headless makes the choice itself; subagent questions skipped (changelog). Still treat `status:"WAITING"` as waiting for input and resume.

### 6. Turn limits
None settable (internal `MAX_INVOCATIONS` not exposed). Use `--print-timeout` + container timeout.

### 7. Custom endpoint
Gemini-API-compatible only: settings `"modelProvider":"gemini"` + env `GEMINI_API_KEY` (the only key var read; not `GOOGLE_API_KEY`, not `.env`) + `GOOGLE_GEMINI_BASE_URL`. Extra models (schema): `{"modelProvider":"gemini","customModelsConfig":{"customModels":{"local":{"modelName":"gemini-api://<base_url>/models/<model>","label":"local","maxTokens":131072,"toolFormatterType":"TOOL_FORMATTER_TYPE_NONE"}}}}` (`customModels` is an object keyed by name; select `--model local`). No OpenAI/Anthropic-compatible endpoints (binary validator accepts only `gemini-api://`, `blade:`, `evergreen:`, `beyond-api://`); Ollama/vLLM need a Gemini-API translation proxy (works: UNVERIFIED). Config w/o touching $HOME: `--settings '<json>'` or a file path (session-only, never saved). No config-dir env var; relocating `~/.gemini` means changing `HOME` (side effects UNVERIFIED).

### 8. Auth in a container
- Best: `GEMINI_API_KEY` + `modelProvider:"gemini"` (docs: the method for headless/CI). ADC: `AGY_ADC_AUTH=true` + gcloud ADC file (+ `GOOGLE_CLOUD_QUOTA_PROJECT`, `GOOGLE_CLOUD_LOCATION`). `AGY_ACCOUNT=<email>` picks an account.
- Subscription OAuth: tokens normally in the OS keyring; on Linux without D-Bus the changelog says it falls back to file storage (file path UNVERIFIED, probably under `~/.gemini/antigravity-cli/`). Headless with no cached credentials fails fast ("authentication required"). The Mac's credentials are in Keychain, so copying `~/.gemini` won't carry them. Possible (UNVERIFIED): log in once interactively in a container with a persistent `~/.gemini` volume and reuse it.

### 9. Files / context
- Auto-loaded rules (docs), from workspace and parents to repo root: `AGENTS.md`, `GEMINI.md`, `.agents/AGENTS.md`, `.agents/GEMINI.md`, `.agents/rules/*.md`, legacy `.agent/rules/*.md`; global `~/.gemini/{AGENTS,GEMINI}.md`, `~/.gemini/config/{AGENTS,GEMINI}.md`, `~/.gemini/config/rules/*.md`. Cannot be switched off; only `.agents/rules.json` `exclude`/`include_only`, or delete/rename the files.
- Hooks: `~/.gemini/config/hooks.json`, `<workspace>/.agents/hooks.json`. State: `~/.gemini/antigravity-cli/`. Possible repo writes (UNVERIFIED): binary strings mention `<workspace>/.gemini/antigravity/{artifacts,transcript.jsonl}`. Exclude `.gemini/`, `.agents/`, `.agent/`, `.metadata.json`.

---

## Gemini CLI 0.34.0 (fallback for "Antigravity with Gemini")

Local: `/opt/homebrew/bin/gemini -> /opt/homebrew/lib/node_modules/@google/gemini-cli/dist/index.js`. Sources: `--help`, package source under `dist/src` and `node_modules/@google/gemini-cli-core/dist/src`, `npm view`.

### 1. Install
`npm i -g @google/gemini-cli@0.34.0` (Node >= 20; verified `npm view`). Pure JS, should work on glibc/musl, arm64/amd64; optional native modules (keytar, node-pty) lack musl/linux-arm64 prebuilds, expected fallback to `child_process` (UNVERIFIED). Non-node images need Node 20+ first.

### 2. Headless
```bash
cd /workspace/repo && GEMINI_CLI_HOME=/cfg gemini -p "$P" -o stream-json --approval-mode yolo -m M
```
- `-p` text is appended to piped stdin. No cwd flag (`--include-directories` adds dirs). Headless always counts as a trusted folder so yolo is not downgraded (`trustedFolders.js`). Without yolo, tools needing confirmation are denied. `security.disableYoloMode` makes yolo throw. `-y` = `--approval-mode yolo`.

### 3. JSON output (verified `output/types.d.ts`, `stream-json-formatter.js`, `nonInteractiveCli.js`)
- stream-json lines: `type` + `timestamp`. Events: `init{session_id,model}`, `message{role,content,delta}` (assistant text arrives as deltas -> concatenate), `tool_use{tool_name,tool_id,parameters}`, `tool_result{tool_id,status,output?,error?{type,message}}`, `error{severity,message}` (loop detected, max session turns), `result{status,error?,stats}`.
- `result.stats`: `total_tokens`, `input_tokens` (prompt incl. cache), `output_tokens`, `cached` (cache reads), `input` (= input_tokens - cached), `duration_ms`, `tool_calls`, `models{<m>:{total_tokens,input_tokens,output_tokens,cached,input}}`. stream-json has NO reasoning, cache-write, cost or per-step usage.
- `-o json`: single object `{session_id,response,stats,error?}`; per-model `stats.models.<m>.tokens{input,prompt,candidates,total,cached,thoughts,tool}` (`thoughts` = reasoning), `.api{totalRequests,...}`, `stats.tools{totalCalls,totalSuccess,totalFail,byName}`, `stats.files{totalLinesAdded,totalLinesRemoved}`.
- Tools (verified `base-declarations.js`): `read_file{start_line,end_line}`, `write_file{content}`, `replace{old_string,new_string,instruction,allow_multiple}`, `read_many_files{include,exclude}`, `list_directory`, `glob`, `grep_search{include_pattern}`, `run_shell_command{command,is_background}`, `web_fetch`, `google_web_search`, `save_memory`, `write_todos`, `activate_skill`, `ask_user`, `enter_plan_mode`, `exit_plan_mode`. Path key names (`file_path`, `dir_path`, `pattern`) UNVERIFIED. Subagent tools are named after the agent: `codebase_investigator`, `cli_help`, `generalist`.
- Shapes (from source):
  ```json
  {"type":"init","timestamp":"...","session_id":"<uuid>","model":"..."}
  {"type":"tool_use","timestamp":"...","tool_name":"read_file","tool_id":"...","parameters":{"file_path":"src/a.py"}}
  {"type":"tool_result","timestamp":"...","tool_id":"...","status":"success","output":"..."}
  {"type":"message","timestamp":"...","role":"assistant","content":"Done.","delta":true}
  {"type":"result","timestamp":"...","status":"success","stats":{"total_tokens":0,"input_tokens":0,"output_tokens":0,"cached":0,"input":0,"duration_ms":0,"tool_calls":0,"models":{}}}
  ```

### 4. Resume
`gemini -p "$MSG" --resume <session-uuid|latest|N> -o stream-json -y` (keeps the same `session_id`; `gemini.js` ~471, `sessionUtils.js`). Sessions stored per project in `~/.gemini/tmp/<project_hash>/chats/` -> same cwd and same `GEMINI_CLI_HOME`.

### 5. Subagents / ask-user
- Built-ins ON by default: `codebase_investigator`, `cli_help`, `generalist` (registered even when `experimental.enableAgents` is false; `agents/registry.js`, `config.js`).
- Disable: `{"agents":{"overrides":{"codebase_investigator":{"enabled":false},"cli_help":{"enabled":false},"generalist":{"enabled":false}}}}`; second layer `"tools":{"exclude":["codebase_investigator","cli_help","generalist"]}` (whether exclude covers subagent tools: UNVERIFIED).
- Enable custom agents (`~/.gemini/agents/`, project): `{"experimental":{"enableAgents":true}}` (schema notes subagents then run in YOLO mode).
- `ask_user` is auto-excluded in `-p` mode (CLI `config.js` 442-448); `tools.exclude:["ask_user"]` makes it explicit.

### 6. Turn limit
`{"model":{"maxSessionTurns":N}}`, default -1. No CLI flag. Each model round-trip = one turn.

### 7. Custom endpoint
Gemini API only: `GEMINI_API_KEY` + `GOOGLE_GEMINI_BASE_URL` (passed by `@google/genai` as `httpOptions.baseUrl`), or `GOOGLE_VERTEX_BASE_URL`. Auth types: `oauth-personal`, `gemini-api-key`, `vertex-ai`, `compute-default-credentials`, `gateway` (semantics of `gateway` UNVERIFIED). No OpenAI/Anthropic compat. Config without $HOME (`utils/paths.js`, `config/settings.js`): `GEMINI_CLI_HOME=/cfg` (reads `/cfg/.gemini/settings.json`); `GEMINI_CLI_SYSTEM_SETTINGS_PATH=/cfg/settings.json` (highest precedence; default `/etc/gemini-cli/settings.json`); also `GEMINI_CLI_SYSTEM_DEFAULTS_PATH`, `GEMINI_CLI_TRUSTED_FOLDERS_PATH`.

### 8. Auth
- Selection order: `GOOGLE_GENAI_USE_GCA=true` (OAuth), `GOOGLE_GENAI_USE_VERTEXAI=true`, `GEMINI_API_KEY`, `GEMINI_CLI_USE_COMPUTE_ADC=true`; setting `security.auth.selectedType` (`oauth-personal`|`gemini-api-key`) wins.
- Subscription: copy `~/.gemini/oauth_creds.json` to `$GEMINI_CLI_HOME/.gemini/oauth_creds.json` (plain file unless `GEMINI_FORCE_ENCRYPTED_FILE_STORAGE=true`; present on this Mac), then `selectedType=oauth-personal` or `GOOGLE_GENAI_USE_GCA=true`.
- Caution: loads `.env` from cwd and parents (precedence UNVERIFIED), so a repo `.env` could inject keys.

### 9. Files / context
- Context file `GEMINI.md`, configurable via `context.fileName` (string|array); loaded from `~/.gemini/`, cwd and parents, subdirs (`context.discoveryMaxDirs`). Disable: point `fileName` at a nonexistent name e.g. `"__none__.md"` (unofficial; UNVERIFIED). `["AGENTS.md"]` reads AGENTS.md instead. `GEMINI_SYSTEM_MD` overrides the system prompt.
- State: `$GEMINI_CLI_HOME/.gemini/tmp/<hash>/chats`, `.gemini/history`. Repo writes: none found (project `.gemini/settings.json` only read; UNVERIFIED) -> exclude `.gemini/`. Skills auto-discovered from `~/.gemini/skills` (14 on this Mac) -> use a clean `GEMINI_CLI_HOME`.
