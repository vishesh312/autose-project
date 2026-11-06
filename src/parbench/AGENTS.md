# AGENTS.md: src/parbench

Read the root `AGENTS.md` first. This file covers the code.

## Modules

| File | Role |
|---|---|
| `cli.py` | argparse entry point: `list-pools`, `bundles`, `build-toy`, `build-images`, `check-gold`, `run`, `report`, `probe`, `cleanup` |
| `config.py` | `Usage` (token accounting), `ModelSpec` (+ list-price cost), `ExperimentConfig`, `.env` loader |
| `dataset.py` | `Pool`, `Feature`, `Bundle`; loads the CooperBench layout (also used by the toy dataset); seeded k-subset sampling; gold conflict report |
| `sandbox.py` | `Container` over the `docker` CLI: exec with in-container timeout, `docker cp` for files (no argv size limits), history scrub, `diff_against` |
| `harnesses/base.py` | `Harness` interface, `ToolCall`, `ParsedRun`, question detection |
| `harnesses/cli_agents.py` | one adapter per CLI: config files + env, headless command, JSON parser |
| `agent_runner.py` | runs one agent: command, nudge loop, timing, usage, tool-call logs, `record.json` |
| `prompts.py` | renders `prompts/*.md` (`string.Template`) |
| `strategies.py` | S0, S1, S2, S4 and the `ID[@template][+extra]` spec syntax |
| `merge.py` | per-agent branches, pairwise trial merges, merge modes naive/union/llm, overlap and patch statistics |
| `grader.py` | k-feature grading via the image's `runner.sh`; ported result parser and test-file filter |
| `runner.py` | experiment expansion, execution, grading, `run.json` metrics |
| `report.py` | `runs.csv` and `summary.md` (Wilson CIs, retention vs. S0) |

## Conventions

- **Usage normalisation.** `Usage.input` is *all* prompt tokens, cached ones included; `cached_input` is the cached subset. Harnesses report this differently (Claude, OpenCode and Pi exclude cache reads from `input`; Codex and Gemini include them), so each adapter converts. A new adapter must do the same.
- **Cumulative counters.** Set `usage_is_cumulative` or `cost_is_cumulative` on a harness whose JSON reports a session-level running total (Codex tokens, Claude cost) so resumed attempts aren't double counted.
- **Metrics sit in `runner.build_record`.** Add a metric there, expose it in `report.flatten`, and document it in `docs/research/Task4_Metrics.md` if it's new.
- **Strategy names are strings** (`S2+plan_first`, `S4@harness_native_worktrees`). A new strategy goes in `strategies.run_strategy`, and a prompt variant is a new file in `prompts/`.
- **Collect diffs with `Container.diff_against`**, which uses a throwaway git index, includes untracked files, and excludes each harness's `repo_artifacts` (e.g. `.claude/`, `.opencode/`).
- **Everything that crosses into a container goes through `put_file` / `put_path`** (`docker cp`). Don't `echo` patches into `bash -c`: large patches break on argv limits.
- **Log everything raw.** `agents/<id>/attemptN.stdout.jsonl` and `.stderr.log` are the source of truth. When a parser is wrong, fix the parser and re-parse the logs; don't re-run the agent.

## Adding a harness

1. Subclass `Harness` in `harnesses/cli_agents.py`: set `name`, `providers`, `supports_subagents`, `repo_artifacts`, and implement `setup` (write config into the container, return env vars), `command` (a shell command run with cwd `/workspace/repo`, prompt read from a file) and `parse`.
2. Register it in `harnesses/__init__.py` and add its install step to `docker/install_harnesses.sh`.
3. Run `parbench probe --toy --harness <name> --model <id>`, read `results/_probes/.../attempt0.stdout.jsonl`, and correct field names against the real output. Then update the UNVERIFIED marks in `docs/harnesses.md`.
4. Check that subagent disabling actually works: with `subagents=False` the log must show zero subagent calls.

## Gotchas

- `merge.merge_mode` writes `.git/info/attributes` for the union driver and removes it afterwards. Keep that cleanup if you edit it.
- S2's merge order is the bundle order (seeded), so results depend on `seed`.
- `grader.grade` splits features across `grade_parallel` containers. With `grade_parallel > 1` on an old Docker Desktop VM with little RAM, typst or HF-datasets images may be killed; lower it.
- Containers are labelled `parbench=1`; `parbench cleanup` removes all of them.
