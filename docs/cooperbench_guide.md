# CooperBench: practical guide for our k-task benchmark

Source read: `github.com/cooperbench/CooperBench` at commit `63b9d44` (14 Sep 2026, package version `0.0.29` + unreleased fixes). All paths below are relative to that repo. We read the code but did not install or run it.

## 0. Terminology mapping (important)

CooperBench uses its words differently from ours ([Task4_Metrics.md](research/Task4_Metrics.md)):

| CooperBench | Ours | Where |
|---|---|---|
| **repo** (e.g. `pallets_jinja_task`) | repo | `dataset/<repo>/` |
| **task** (`task1621`): one upstream PR at one base commit | **pool** | `dataset/<repo>/task<id>/` |
| **feature** (`feature3`): one slice of the PR, with its own tests | **task** | `dataset/<repo>/task<id>/feature<N>/` |
| **pair** (2 features of one task) | bundle with *k* = 2 | `dataset/subsets/*.json` |
| `solo` setting | S1 | `src/cooperbench/runner/solo.py` |
| `coop` setting | S2 without a resolver (plus messaging) | `src/cooperbench/runner/coop.py` |
| `team` setting (lead + members, shared task list) | close to S4 / S2 with a leader | `src/cooperbench/runner/team.py` |

In the rest of this guide, "task" and "feature" follow **CooperBench's** meaning unless we say "our task".

## 1. Dataset structure

**Where it lives.** The full dataset is **in the GitHub repo** under `dataset/`: 774 files, **4.8 MB**. A mirror is on HuggingFace at `CodeConflict/cooperbench-dataset`. `cooperbench prepare` downloads the mirror into `./dataset` (`src/cooperbench/dataset.py`, `huggingface_hub.snapshot_download`). `dataset/README.md` says the harness, the images and the dataset are "versioned together", so we should take the `dataset/` tree from a pinned git commit. We did not check the size of the HF copy.

**Size.** 12 repos, **30 tasks (our pools), 199 features, 652 pairs** (the sum of C(n,2) over the tasks). The README's "Tasks: 652" really counts pairs. Languages: Python (9 repos), Go (`go_chi`), TypeScript (`react_hook_form`), Rust (`typst`).

**Layout per task** (`dataset/<repo>/task<id>/`):

| File | What it is |
|---|---|
| `Dockerfile` | `FROM <lang image>`, then `git clone <upstream> repo && git checkout <BASE_SHA>` into `/workspace/repo`, then installs deps. **The base commit is here** (also as `BASE_COMMIT=` in `setup.sh`). |
| `runner.sh` | **The grading script.** It is baked into the image as `/usr/local/bin/runner.sh` (and is also the image `ENTRYPOINT`). |
| `run_tests.sh`, `setup.sh`, `test_features.sh` | Older host-side helpers. `test_features.sh` hard-codes the author's laptop paths, so ignore it. |
| `combined.patch` | The **whole PR with every feature in one tree**, conflicts already resolved. It passes every feature's tests (`scripts/check_combined.py`). |
| `meta_tests.patch` | Only in some tasks (e.g. jinja 1465/1559). Not used by the eval code. |
| `feature<N>/feature.md` | The feature description. This is exactly what the agent is shown. |
| `feature<N>/feature.patch` | Gold implementation of this feature **alone**, against the base commit. |
| `feature<N>/tests.patch` | Hidden tests. They must fail on base and pass with gold. |
| `feature<N>/feature.filtered.patch` | Only in jinja 1621. Not used by the eval. |

**Dataset metadata files:**
- `dataset/subsets/*.json`: `all` (652 pairs), `lite` (100), `flash` (50), `flash_10`, `core` (10), `team3_250` (250 triplets, under a `pairs` key), `team3_all` (every triplet, under a `groups` key).
- `dataset/gold_conflict_report.json`: the result of a pairwise `git merge` of gold `feature.patch` files for all 652 pairs. **499 of 652 (76.5%) conflict.** Produced by `scripts/check_gold_conflicts.py`.
- `dataset/SPEC_AUDIT.md` and `.spec_audit_verdicts.json`: a log of edits to `feature.md` and `tests.patch` (`OK` 164 / `SPEC` 23 / `TEST` 12). Specs and tests **have changed over time**, so pin a commit.

**Per-pool summary** (computed from the dataset; "clean3/4" = number of 3- or 4-feature subsets in which **every** gold pair merges cleanly):

| pool | n | gold-conflicting pairs | clean3 | clean4 | lang / base image |
|---|---|---|---|---|---|
| dottxt_ai_outlines/1371 | 4 | 6/6 | 0/4 | 0/1 | py3.11 |
| dottxt_ai_outlines/1655 | 10 | 28/45 | 8/120 | 0/210 | py3.11 |
| dottxt_ai_outlines/1706 | 8 | 27/28 | 0 | 0 | py3.11 |
| dspy/8394 | 5 | 9/10 | 0 | 0 | py3.11 |
| dspy/8563 | 6 | 7/15 | 3/20 | 0 | py3.11 |
| dspy/8587 | 6 | 14/15 | 0 | 0 | py3.11 |
| dspy/8635 | 6 | 8/15 | 2/20 | 0 | py3.11 |
| go_chi/26, 27 | 4, 4 | 6/6, 6/6 | 0 | 0 | golang alpine |
| go_chi/56 | 5 | 8/10 | 0 | 0 | golang alpine |
| huggingface_datasets/3997, 6252, 7309 | 5, 6, 2 | 8/10, 8/15, 1/1 | 0 | 0 | py3.12 |
| llama_index/17070, 17244, 18813 | 3, 7, 6 | 3/3, 12/21, 13/15 | 0, 3/35, 0 | 0 | py3.10 |
| openai_tiktoken/0 | 10 | 45/45 | 0 | 0 | py3.11 |
| pallets_click/2068, 2800, 2956 | 12, 7, 8 | 66/66, 12/21, 17/28 | 0, 3, 4 | 0 | py3.11 |
| pallets_jinja/1465 | 10 | 45/45 | 0 | 0 | py3.11 |
| pallets_jinja/1559 | 10 | 8/45 | 66/120 | 60/210 | py3.11 |
| pallets_jinja/1621 | 10 | 18/45 | 26/120 | 8/210 | py3.11 |
| pillow/25, 290, 68 | 5 each | 7, 8, 9 of 10 | 0 | 0 | py3.11 |
| react_hook_form/153, 85 | 6, 5 | 15/15, 4/10 | 0, 4/10 | 0, 1/5 | node 22 + pnpm |
| samuelcolvin_dirty_equals/43 | 9 | 36/36 | 0 | 0 | py3.11 |
| typst/6554 | 10 | 45/45 | 0 | 0 | rust 1.80 |

This matches our earlier counts: 28 of 30 pools have ≥4 features, 18 have ≥6, 10 have ≥8.

## 2. Environment and grading

**Images.** There is one prebuilt image per task on Docker Hub: `akhatua/cooperbench-<repo-without-_task, _→->:task<id>`, e.g. `akhatua/cooperbench-pallets-jinja:task1621` (`src/cooperbench/utils.py::get_image_name`). The repo is at `/workspace/repo`, checked out at the base commit.

**Architecture: arm64 is fine.** All 30 images are multi-arch (linux/amd64 + linux/arm64). We checked this through the Docker Hub API on 2026-11-06, and `dataset/README.md` and `CHANGELOG.md` say the same (arm64 was added for react-hook-form 153/85 and HF-datasets 3997 in the unreleased section). Nothing in the code pins `--platform`, so on our M5 Mac Docker pulls the arm64 build natively. The authors say all 199 features pass gold on both architectures (`scripts/check_gradeable.py --backend docker`, `scripts/check_combined.py --backend docker`).

**Image sizes** (compressed, arm64): the total for all 30 is **about 28 GB**. The large ones are outlines 1655/1706 (~4 GB each), HF-datasets 6252 (3.8 GB), typst (2.4 GB) and HF-datasets 7309 (1.05 GB arm64 vs 5.45 GB amd64). Most Python pools are 0.25–1 GB, and go_chi is about 0.1 GB. Expect 2–3× more disk once unpacked.

**Grading entrypoint** (`src/cooperbench/eval/sandbox.py`):
1. Start the container with the entrypoint cleared: `docker run --entrypoint "" <image> sleep infinity` (`eval/backends/docker.py`).
2. Write the patches into `/patches/`.
3. For each feature, run `_run_tests()`:
   ```bash
   cd /workspace/repo
   git checkout --force $BASE_SHA && git reset --hard $BASE_SHA && git clean -fd   # no -x: keeps prebuilt artefacts
   bash /usr/local/bin/runner.sh tests<N>.patch merged.patch                      # args are filenames under /patches
   ```
   `runner.sh <tests_patch> [feature_patch]` applies both patches with `git apply` (falling back to `--3way`), re-installs the package (for example `pip install -e ".[test]"`), and runs that feature's test file(s). Example: jinja 1621 runs `python -m pytest tests/test_loader.py -v`. dspy also runs every file that `tests.patch` touches.
4. **A feature passes when** `exit_code == 0 and parsed_passed > 0`. `_parse_results` uses regexes for pytest, go test, cargo and jest/vitest.
5. Before step 3, `_filter_test_files()` removes any test file the agent wrote from its patch (`_TEST_DIR_RE`, `_TEST_FILE_RE`). Otherwise it would collide with `tests.patch`.

**Can it grade an arbitrary tree with more than 2 features? Yes, with a small wrapper.** `runner.sh` takes **one** feature patch, so we pass it **one diff of the final tree against `BASE_SHA`**, then run it once per feature's `tests.patch`. `test_solo()` already does exactly this, but only for 2 features (`feature1_id`, `feature2_id`). The Python layer is pair-only:
- `evaluate.py::_evaluate_single` does `f1, f2 = features[0], features[1]`.
- `test_merged`/`test_solo` take exactly two features.
- `runner/tasks.py::discover_tasks` does `f1, f2 = pair`, so the triplet subsets would crash or be cut down to two.

So for *k* > 2 we write about 80 lines: a loop over `test_solo`'s inner logic. Reuse `_run_tests`, `_parse_results` and `_filter_test_files`, ideally copied rather than imported.

**Their merge policy (current code)** is in `test_merged`:
- If the two patches are byte-identical, skip the merge.
- Otherwise run a naive `git merge` (agent2 branch ← agent1 branch).
- If that conflicts, grade **agent1's patch alone** against both test suites (the "lead fallback").

There is **no union step and no LLM resolver** any more. The CHANGELOG entry for `test_merged` and `docs/BENCHMARK_RESULTS.md` say union was dropped. The paper's pipeline (git merge → union → LLM) is in old commit `95cd5a2` (22 Jan 2026), file `src/cooperbench/evaluation/llm_merge.py`. It resolved each conflict hunk with a strict "merge both, add nothing" system prompt, through litellm, against a local model server at `:8457`. The v0.2.0 rewrite (`f6fb34f`) removed it. If we want to match the paper's merge numbers, we have to re-implement this.

## 3. Pairs, pools and k > 2

- **How pairs are chosen:** every C(n,2) combination inside one task (`discover_tasks`), or a seeded uniform sample from that set (`lite`/`flash`, `random.seed(42)`, see `dataset/README.md`). Nothing else constrains the choice.
- **Nothing stops 3+ features from the same pool.** The coop and team runners already start N agents (`n_agents = len(features)` in `runner/coop.py` and `runner/team.py`), and `team3_250.json`/`team3_all.json` list triplets. Only the eval is limited to 2 (see §2). The paper's own *k* = 3/4 result (our Task 4 cites 68.6 → 46.5 → 30.0%) must have used code that is not in this repo, or code that is no longer there. **Unverified.**
- **Gold patches do not merge with each other** in most pools: 76.5% of pairs conflict, because the features were carved out of one PR and touch the same lines. `dataset/README.md` says this is on purpose. **Only jinja 1559, jinja 1621, outlines 1655 and a few others have gold 3-subsets that merge cleanly** (table above). For almost every *k* ≥ 3 bundle, the gold patches will conflict.
- **A joint gold solution does exist: `combined.patch`.** It contains **all n features** of the pool, so it is a *superset* oracle for any bundle: it must pass every bundle feature's tests. There is no gold tree containing only a chosen subset. Assuming each feature's tests check only that feature, the superset is a valid upper-bound oracle.

## 4. Agent harness

- **Adapters** live in `src/cooperbench/agents/`:
  - `mini_swe_agent_v2` (default; an in-repo fork of mini-SWE-agent; `step_limit: 100`, `cost_limit: 3`)
  - `swe_agent`
  - `openhands_sdk` (vendored; needs Modal for both run and eval)
  - `claude_code`
  - `codex`
- **Plug-in interface:** `AgentRunner.run(task, image, ...) -> AgentResult` (`agents/__init__.py`). External adapters register through `COOPERBENCH_EXTERNAL_AGENTS=<module>` and `@register("name")` (`agents/README.md`). **There is no OpenCode or Pi adapter.**
- **How `claude_code` runs** (`agents/claude_code/adapter.py`, `setup.sh`):
  1. Run `npm i -g @anthropic-ai/claude-code` **inside the task container**.
  2. Run it headless: `claude --print --output-format=stream-json --permission-mode=bypassPermissions [--max-turns N] [--disallowedTools ...]`.
  3. The agent is told to write `git diff > /workspace/repo/patch.txt`, and the adapter reads that file (`agents/_coop/prompt.py`).
  4. `--base-url` points it at vLLM's Anthropic-compatible `/v1/messages`. The adapter rewrites `localhost` to `host.docker.internal` (`docs/QWEN_LOCAL.md`).
  5. There is a "qwen" profile that disables Task/subagent tools. `codex` follows the same pattern.
- **What gets logged** (per run, under `logs/<run>/<setting>/<repo>/<task>/f1_f2/`):
  - `result.json`: per-agent status, cost, steps, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, patch lines, and the run's `started_at`/`ended_at`/`duration_seconds`.
  - `agent<N>.patch` or `solo.patch`
  - `agent<N>_traj.json` (messages)
  - `conversation.json` (messages between agents)
  - `eval.json`
  - team mode also writes a `metrics` block

  **Not logged:** per-call timestamps, reasoning tokens, or tool-call file lists. The raw claude stream/session JSONL (`*_stream.jsonl`, `*_session.jsonl`) has most of this, and `agents/claude_code/parsers.py` parses it.
- **Reuse vs. write ourselves:**

| Reuse (copy, MIT licensed) | Write ourselves |
|---|---|
| Dataset tree, images, `runner.sh` | k-feature grader loop |
| `_run_tests`, `_parse_results`, `_filter_test_files`, branch/merge shell snippets (`sandbox.py`) | k-way merge in a fixed order + union + LLM resolver (port from `95cd5a2`'s `llm_merge.py`) |
| History scrub `_detach_upstream` (`agents/mini_swe_agent_v2/connectors/git.py`) | OpenCode / Pi adapters, and S3 planner/scheduler |
| claude_code / codex in-container install and headless command lines, stream-json parsers | Per-call/tool-call logging, wall-clock and parallelism tracking |
| `gold_conflict_report.json` | Pairwise trial merges of *agent* patches (conflict rate) |

## 5. Packaging and CLI

- **Install:** `pip install cooperbench` (Python ≥3.10 per `pyproject.toml`; the README says 3.12+), or `uv`/`pip install -e ".[dev]"`.
- **Dependencies are heavy and installed by default:** `modal`, `google-cloud-aiplatform`, `litellm`, vendored `openhands-sdk/tools/workspace`, `redis`, `docker`, `huggingface-hub` and more. `runner/coop.py` and `runner/team.py` run `import modal` at module level.
- **Commands** (`src/cooperbench/cli.py`):
  - `cooperbench prepare`
  - `cooperbench config gcp`
  - `cooperbench run -n NAME [-s subset] [-r repo] [-t task] [-f 1,2] [-m model] [-a agent] [--setting solo|coop|team] [--backend docker|modal|gcp] [--git] [--no-messaging] [--no-auto-eval] [--base-url URL --auth-token T] [--dataset-dir] [--log-dir]`
  - **Eval only:** `cooperbench eval -n NAME [-s subset] [-r] [-t] [-f] [-c 10] [--backend docker] [--force]`. It finds runs from the `logs/` layout and needs `agent<f>.patch` or `solo.patch` there. It is pair-only.
- **The CLI's default backend is `docker`.** The README still says `modal`. The default model is `vertex_ai/gemini-3-flash-preview`.
- Coop mode needs Redis (`docker run -p 6379:6379 redis:7`).
- Python API: `from cooperbench import run, evaluate`.

## 6. Gotchas

1. **Future commits leak.** The Dockerfiles `git clone` the full upstream repo and then `git checkout <sha>`, so later commits (often the real implementation) stay reachable through `origin/*`, tags and the default branch. CooperBench only removes them in `GitConnector._detach_upstream`, which is used in `--git` coop mode. **We must run that scrub before any agent starts.**
2. **Grading probably needs network.** Most `runner.sh` files re-run `pip install -e .`, `pnpm`, etc. on every graded feature. We did not check whether it works offline.
3. **Size limit when writing patches.** `_write_patch` pushes base64 through one `bash -c "echo '…'"` argument. Linux caps a single argument at 128 KiB, and CooperBench already hit a 64 KiB limit on Modal with jinja 1465's 107 KB `combined.patch`. A merged *k* = 6 diff can exceed this. **Use `docker cp` or a bind mount instead.**
4. **The `runner.sh` in the image is the real grader.** Editing `dataset/.../runner.sh` has no effect until the image is rebuilt (`scripts/rebuild_task_images.sh`). Read `/usr/local/bin/runner.sh` from the image.
5. **A feature's whole test file runs**, including the old tests in it. A bundle that breaks unrelated behaviour in that file fails that feature.
6. **Pass/fail comes from regexes** (`(\d+) passed` and similar) plus the exit code. Tests are wrapped in `timeout 300`, and each exec in the sandbox times out at 600 s. typst compiles Rust and can hit timeouts or memory limits under Docker Desktop. **Give Docker at least 8–12 GB of RAM.**
7. **We found no flaky-test list.** CooperBench's defect fixes are in `SPEC_AUDIT.md` and the CHANGELOG (24 features were ungradeable before 0.0.29, and 19 more were fixed later). Timing-based features such as jinja 1621 f9 "monitoring/auto_reload" may be flaky. **Unverified.**
8. **The lead-alone fallback** in `test_merged` gives a pass to agent1's patch alone when the merge conflicts. That does not match our "lost in merge" metric, so don't copy it.
9. **The two architectures differ.** The outlines 1371 arm64 image is 0.54 GB vs 4.55 GB for amd64, so the dependency stacks are different. **Run all comparisons on one architecture** (local arm64).
10. **Required keys:** whatever LLM key the harness uses. `HF_TOKEN` is optional. Modal/GCP are needed only for those backends. `openhands_sdk` runs require Modal.

## 7. How we will use it

1. **Pin and vendor the data.** Copy `dataset/` from commit `63b9d44` into our repo (5 MB) or a submodule. Don't use `cooperbench prepare`; it gives us no control over the version.
2. **Build a bundle manifest** with one JSON row per bundle: `{repo, task_id, image, base_sha, features[k], seed_order, gold_conflict_pairs, gold_files[f]}`.
   - Sample C(n,k) subsets per pool with a fixed seed, for *k* ∈ {2,3,4,6}, from pools with n ≥ k (28/28/28/18 pools).
   - `base_sha` comes from the Dockerfile `git checkout` line. `gold_files` comes from `feature.patch` headers, skipping test files.
   - `gold_conflict_pairs` comes from `gold_conflict_report.json`. It gives our Task 3 conflict-density strata and the ground truth for S3's conflict prediction.
3. **Agent sandboxes.** Use one container per agent, all from the task image.
   - Run `_detach_upstream` first, then install the harness CLI (as `agents/claude_code/setup.sh` does).
   - Run the harness headless against `/workspace/repo`, with Ollama/vLLM reached via `host.docker.internal`.
   - **Collect `git diff $BASE_SHA` ourselves** instead of trusting an agent-written `patch.txt`.
   - Our S1 is one container with all *k* `feature.md` files joined, in the same format as `runner/solo.py::_spawn_solo_agent`.
   - S4 is one container with the harness's subagents enabled.
4. **Merge stage** (S2/S3/S4, run in a fresh container from the same image):
   - Make one branch per agent off `BASE_SHA`.
   - Record a trial `git merge` for every pair (this gives the conflict rate).
   - Then merge in the bundle's fixed order: naive, then union, then an LLM resolver ported from `llm_merge.py`, using the same model as the agents.
   - Log every step.
   - Output one `final.diff` against `BASE_SHA`.
5. **Grader** (`grade_bundle(image, base_sha, features, final.diff)`):
   - Run `_filter_test_files` on the diff.
   - `docker cp` the diff and each `tests.patch` into `/patches`.
   - For each feature, reset to base and run `bash /usr/local/bin/runner.sh tests_f.patch final.diff`.
   - Pass = exit 0 and parsed passed > 0. Save the output for each feature.
   - Also grade every agent's own diff alone. That gives the "lost in merge" metric.
6. **Check the grader before any agent runs.** For every pool and feature on local arm64:
   - (a) tests alone must fail;
   - (b) `feature.patch` must pass (this is the S0 oracle);
   - (c) `combined.patch` must pass every feature (the bundle oracle).
   - Then for k = 2 only, compare our grader with `cooperbench eval --backend docker` on a few `flash` pairs to check that we match their numbers.
7. **Pilot calibration against CooperBench.** Optionally run `cooperbench run --setting solo|coop -a claude_code -f i,j` in a separate venv on 5–10 `flash` pairs to check our *k* = 2 numbers against theirs. Everything with *k* > 2 goes through our own pipeline.

## Not verified

- The size and contents of the HF mirror.
- Whether grading works offline.
- The flakiness of specific tests.
- How the paper ran *k* = 3/4; that code is not in this repo.
- Which resolver model the paper used. The old code calls `openai/gpt-3.5-turbo` through a local server at `:8457`.
- Any claim of "verified on both architectures". We are taking the authors' word (`CHANGELOG.md`) and have not re-run their checks.
