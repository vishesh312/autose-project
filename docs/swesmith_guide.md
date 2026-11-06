# SWE-smith: practical guide for our k-task bundle benchmark

Researched 2026-11-06. We read the SWE-smith repo (shallow clone at commit `9b74ac0`, read only; nothing installed or run), the docs site, the paper PDF (arXiv v2) and the Hugging Face pages. Citations are `[n]` (see Sources). Statements marked **Inference:** are our own reasoning, not claims by the authors. **UNVERIFIED** means we could not confirm it from a source. Paths like `swesmith/...` are relative to the SWE-smith repo.

## 1. What SWE-smith is

- **Problem it solves.** Training data for SWE agents is small and expensive, because SWE-bench-style collection needs a separate execution environment per task instance. The paper says the datasets are "small, costly to build" and their environments take "terabytes" [8]. SWE-smith inverts the order: build one execution environment per repository first, then synthesise many task instances inside it [8, §2]. It is "a toolkit for training SWE-agents" that can "Turn any Github repository into a SWE-gym" [1].
- **Headline numbers.** 50k task instances (50,137 in Table 1) from 128 Python repositories; SWE-agent-LM-32B reaches 40.2% pass@1 on SWE-bench Verified [8; 3].
- **Instance format.** The paper (App. A.1) lists the fields: `repo`, `instance_id` ("usually (repo).(bug type).(hash)"), `base commit` (a branch pointing to the repo with the bug applied), `patch` ("The diff that causes the bug... Reverting this patch is effectively the solution"), `problem statement`, `created at`, `FAIL_TO_PASS`, `PASS_TO_PASS` [8]. The Hugging Face card shows seven columns: `instance_id`, `patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `image_name`, `repo`, `problem_statement` [9]. The gather step writes `instance_id, repo, patch, FAIL_TO_PASS, PASS_TO_PASS, image_name` [6].
- **Difference from SWE-bench.** No `version`, no environment-setup commit, no `hints_text`. Most important for us: "There is no test patch field, as the SWE-smith collection pipeline does not create or synthesize any hidden tests. All FAIL TO PASS bugs are visible and runnable in the repository at inference time" [8, A.1]. The task formulation is "identical to the definition put forth by SWE-bench" [4].
- **Success definition.** A candidate is kept only if it breaks 1 or more previously passing tests (FAIL_TO_PASS, "F2P"). The docs add that a valid instance needs 1+ F2P and 1+ PASS_TO_PASS tests [6]. A solution is graded by the evaluation harness (`python -m swesmith.harness.eval --dataset_path ... --predictions_path ... --run_id ...`) [6].
- **Direction of the task.** The agent starts from the **buggy** tree (the bug patch applied) and has to repair it. The gold fix is the reverse of `patch` [8, A.1]. This differs from CooperBench, where the agent starts from the clean base and implements a feature (see our `docs/cooperbench_guide.md` [23]).
- **Task statistics.** Median per instance: 6 F2P tests, 5 edited lines overall (Table 1) [8]. By strategy (Table 12, median, IQR): Combine edits 2 functions, 1 file (IQR 1-2); LM edits 1 function, 1 file; PR Mirror 2 functions; Procedural 1 function, 1 file [8].

## 2. Pipeline step by step

Quickstart script sequence from the docs [2]:

```bash
python -m swesmith.bug_gen.llm.modify pandas-dev__pandas.95280573 \
    --config_file configs/bug_gen/lm_modify.yml --model claude-3-7-sonnet-20250219 --n_bugs 1 --n_workers=20
python -m swesmith.bug_gen.collect_patches logs/bug_gen/pandas-dev__pandas.95280573/
python -m swesmith.harness.valid logs/bug_gen/pandas-dev__pandas.95280573_all_patches.json --workers 8
python -m swesmith.harness.gather logs/run_validation/pandas_test
python -m swesmith.issue_gen.generate --dataset_path logs/run_validation/basic/pandas_test.json \
    --model claude-3-7-sonnet-20250219 --n_workers=1 --config_file configs/issue_gen/ig_v2.yaml --experiment_id ig_v2
```

### 2a. Execution environment

- **Paper procedure.** Run SWE-agent for at most 100 steps on the latest commit to install the repo and run its tests; manually verify; keep the repo if more than 80% of tests pass; build a Docker image [8, §2.1]. App. A.2: average cost $0.72 and 17 steps per run, runs "typically finish within two minutes", manual review 3-20 min, 18 human hours for 128 repos, and the author "gave up on 17 repositories" [8]. The docs say the automatic SWE-agent install step is "Coming soon!" in the docs [5].
- **Repo code path.** Each repository + commit is a `RepoProfile` subclass in `swesmith/profiles/*.py` with `owner`, `repo`, `commit`, a `dockerfile`, `test_cmd`, a `log_parser`, and `timeout` (default 90 s per instance) / `timeout_ref` (default 900 s for the whole suite) [16; 17]. `python_version` defaults to "3.10" in the base class, and some Python profiles override it (e.g. "3.11", "3.12") [19]. One profile = one commit, so all bugs for a repo share one base commit (see §5).
- **Build command.** `python -m swesmith.build_repo.create_images -r MonkeyType` creates (1) a mirror of the repo at that commit under the GitHub org `swesmith` and (2) a Docker image `swesmith.x86_64.<repo>.<commit>`. Without `-r` it builds "all SWE-smith repositories (300+ as of 12/2025)"; `-f` forces a rebuild [5].
- **Prebuilt images.** `python -m swesmith.build_repo.download_images` downloads them [5]. The code constructs image names as `swebench/swesmith.<arch>.<owner>_1776_<repo>.<commit8>` (lower-cased) [16, 18]. The README advertises "250+ Environments, one Docker image per repo" and the assets page "128 GitHub repositories" [1, 3]. Counts disagree across sources (128 / 222 / 250+ / 300+), so treat them as **UNVERIFIED** and check Docker Hub `swebench/` ourselves. Total size: paper says 295 GB for the 128 environments (Table 2) [8]. Per-image sizes: UNVERIFIED.
- **Platform.** "SWE-smith requires Docker... developed and tested on Ubuntu 22.04.4 LTS. We do *not* plan on supporting Windows or MacOS" [1]. Our own CooperBench guide says its images are multi-arch; SWE-smith's container code hard-codes `platform="linux/x86_64"` [16], so on Apple Silicon expect emulation (**Inference**).

### 2b. Bug synthesis: every strategy documented

All write artifacts under `logs/bug_gen/<repo>/`: `bug__<bug_type>__<hash>.diff` and `metadata__<bug_type>__<hash>.json` [4].

| # | Strategy (paper name / artifact name) | Command | How it works | Knobs |
|---|---|---|---|---|
| 1 | **LM Modify** (`lm_modify`) | `python -m swesmith.bug_gen.llm.modify $repo --n_bugs 1 --model <m> --config_file configs/bug_gen/lm_modify.yml` | For each function/class entity, prompt an LM to introduce a bug [4]. | `--config_file/-c`, `--model`, `--n_bugs/-n`, `--max_bugs/-m`, `--n_workers/-w` (from argparse in `swesmith/bug_gen/llm/modify.py`) |
| 2 | **LM Rewrite** (`lm_rewrite`) | `python -m swesmith.bug_gen.llm.rewrite $repo --model <m> --config_file configs/bug_gen/lm_rewrite.yml --n_workers 1` | Given only the function header + docstring, the LM rewrites it from scratch; it is not asked for a bug, so yield is lower [4; 8 §2.2]. | same style flags |
| 3 | **Procedural Modification** (`func_pm_*`) | `python -m swesmith.bug_gen.procedural.generate $repo --max_bugs 10` | Parse each entity to an AST (Python), apply a transformation when the entity meets criteria, unparse [4]. | `--seed/-s` (24), `--max_bugs` (-1), `--interleave/-i`, `--max_entities`, `--max_candidates`, `--timeout_seconds/-t` (`procedural/generate.py`) [15]. Each modifier has `likelihood` and `min_/max_complexity` [15]. |
| 4 | **Combine Bugs, same file** (`combine_file`) | `python -m swesmith.bug_gen.combine.same_file logs/bug_gen/<repo> --num_patches 3 --limit_per_file 15 --max_combos 100` | Combine validated function-level bugs from one file [4, 12]. | `num_patches`, `limit_per_file`, `max_combos`, `--include_invalid_patches` [12] |
| 5 | **Combine Bugs, same module** (`combine_module`) | `python -m swesmith.bug_gen.combine.same_module logs/bug_gen/<repo> --num_patches 2 --limit_per_module 20 --max_combos 200 --depth 2` | Combine validated bugs under the same sub-directory; only patches editing 2+ files are saved [4; 8 §B.3]. | `num_patches`, `limit_per_module`, `max_combos`, `depth` [4] |
| 6 | **PR Mirror / Invert PRs** (`pr_mirror`) | `python -m swesmith.bug_gen.mirror.generate $file --model openai/o3-mini` | Takes SWE-bench-style PR candidates (`<repo>-task-instances.jsonl.all`; PR must link 1+ issue and edit 1+ code file), asks an LM to revert the PR file by file, so the candidate undoes the PR [4]. The docs' artifact section for this strategy is empty [4]. | `--model` |

Procedural modifier names (all from `swesmith/bug_gen/procedural/base.py`, `CommonPMs`): `func_pm_class_rm_base`, `func_pm_class_rm_funcs`, `func_pm_class_shuffle_funcs`, `func_pm_ctrl_invert_if`, `func_pm_ctrl_shuffle`, `func_pm_op_change`, `func_pm_flip_operators`, `func_pm_op_swap`, `func_pm_op_break_chains`, `func_pm_op_change_const`, `func_pm_inc_dec_flip`, `func_pm_aug_assign_swap`, `func_pm_bool_negate`, `func_pm_remove_loop`, `func_pm_remove_cond`, `func_pm_remove_assign`, `func_pm_loop_break_continue_swap`, plus `func_pm_remove_wrapper` in the Python module [15]. The docs and the paper say "13 (and counting)" [4; 8 Table 8]; the code has more.

LM prompt config files live in `configs/bug_gen/` (`lm_modify.yml`, `lm_rewrite.yml`, `class_basic.yml`, `func_fun.yml`), with fields `name`, `criteria`, `parameters`, `system`, `demonstration`, `instance`, and an optional criteria function that filters which functions are eligible [20]. The shipped `lm_modify.yml` prompt includes "For longer functions, if there is an opportunity to introduce multiple bugs, please do!" [20].

Large-scale generation + validation: `modal run scripts/bug_gen.py --language javascript [--repos ...] [--show-stats]` (Modal cloud, two phases: generate then validate) [4]. Note: the docs write `scripts/bug_gen.py`, but the repo file is `scripts/bug_gen_modal.py` [directory listing, 1].

### 2c. Validation

`collect_patches` writes `logs/bug_gen/<repo>_all_patches.json`; then `python -m swesmith.harness.valid <that json> [--workers N]`. It first runs the original test suite (pre-gold), then applies each candidate and re-runs; a candidate that "breaks 1+ existing tests" is usable [6]. Per instance it writes `eval.sh`, `patch.diff`, `report.json` (F2P and P2P), `run_instance.log`, `test_output.txt` under `logs/run_validation/<run_id>/<instance_id>/` [6]. Then `python -m swesmith.harness.gather logs/run_validation/<run_id>` writes `logs/task_insts/<run_id>.json` and creates **one git branch named `<instance_id>` per valid instance** in the mirror repo, with the bug patch applied [6]. Paper: a 2-minute test runtime limit (candidates exceeding it are discarded) [8, §2.1]. Code: `valid.py` reports statuses `timeout`, `fail`, `0_f2p`, `1+_f2p` [21]. The repo's `get_container` pulls the image and runs `git checkout <instance_id>` in the working dir [16].

### 2d. Issue text

`python swesmith/issue_gen/generate.py logs/task_insts/<repo>.json --config_file configs/issue_gen/ig_v2.yaml --model anthropic/claude-3-7-sonnet-20250219 --n_workers 4 --experiment_id ig_v2 --use_existing` [7]. Output goes to `logs/issue_gen/<repo>__ig_v2_n1.json` with a `problem_statement` field. The paper's recipe: give the LM the diff, the source of a random F2P test, and the test output on the buggy tree, and ask for GitHub-issue-style text with reproduction code [8, §2.1]. Average cost: 2.54 cents per issue [8, §2.2]. Alternatives (no LM): `get_static.py` (one of 7 static templates), `get_from_tests.py` (a random F2P test as the statement), `get_from_pr.py` (original issue, only for some PR mirrors) [7]. Configs: `ig_v1.yaml`, `ig_v2.yaml`, `ig_tests.yaml` [1 dir listing].

### 2e. Export / loading

Hugging Face: `load_dataset("SWE-bench/SWE-smith", split="train")`, then `registry.get_from_inst(task)` returns the `RepoProfile` and `rp.get_container(task)` returns a Docker container with the instance checked out [1]. There is also a `scripts/upload_tasks_to_hf_modal.py` for pushing per-language sets [repo file]. Optional difficulty rating: `docs/guides/difficulty_rating.md` and SWE-Rater-32B [3] (not read in detail).

## 3. Scale and cost numbers (as stated)

| Item | Number | Source |
|---|---|---|
| Instances / repos | 50k (50,137) / 128 Python repos; avg 381 per repo, up to 2,277 for pandas | [8, §2.2, Table 1] |
| Yield by strategy | Combine 96.9% (10,092 inst.); LM Modify 56.0% (17,887); LM Rewrite 35.0% (4,173); PR Mirror 33.8% (2,344); Procedural 40.2% (15,641); total 50.1% | [8, Table 1] |
| Cost per candidate | Combine 0.00 cents; Procedural 0.00; LM Modify 0.38 cents; LM Rewrite 3.93 cents; PR Mirror 5.53 cents; avg 2.32 cents | [8, Table 1] |
| Total creation cost | $1,360 ($1,000 bugs, $160 auto-install, $200 issues for 10K bugs); issue 2.54 cents each | [8, §2.2] |
| Human effort | ~20 h for one author overall | [8, §2.1] |
| Flask case study | 267 valid instances from 402 candidates; 23 min, $2.47 (~$0.00613 per instance) for bug gen; validation 14 min | [8, App. C] |
| Env storage | 295 GB for 128 repos vs 50 to 150 TB estimated for SWE-bench-style | [8, Table 2, §2.2] |
| Expert trajectories | 8,686 task instances attempted, 17,906 attempts, 36% resolve; 5,016 training trajectories (README says 26k trajectories released) | [8, §3; 1] |
| Results | SWE-agent-LM-32B: 40.2% Verified, 30.7% Lite (5k train); SWE-agent-LM-7B: 15.2% Verified, 11.7% Lite (2k train); all pass@1 | [8, Table 3] |
| Difficulty | mean rating 5.27-5.72 across strategies vs SWE-bench 5.01, SWE-gym 5.62 | [8, §2.2] |
| HF dataset | 278 MB; viewer shows 59.1k rows while card text says 50,137; MIT; card says "We will no longer actively update this dataset" (12/14/2025) and points to per-language sets | [9] |

## 4. Language support

- **Paper (April/May 2025):** Python only. "SWE-smith's collection pipeline is Python-centric... rely heavily on the Python specific `ast` library. That said, SWE-smith's collection strategy is transferable to other languages" [8, Discussion].
- **Repo today (checked out Nov 2026):** adapters for C, C++, C#, Go, Java, JavaScript, PHP, Python, Ruby, Rust, TypeScript in `swesmith/bug_gen/adapters/` and profiles for the same languages in `swesmith/profiles/` [repo dirs]. Procedural modifier modules exist for Python, Go, Rust, Java, JavaScript, C++, PHP, Ruby; the TypeScript procedural folder only contains `__init__.py` in our clone [repo dirs]. Go and Rust profiles exist and use `go test -v ./...` for Go [19].
- **Per-language datasets on Hugging Face:** `SWE-bench/SWE-smith-py`, `-go`, `-rs`, `-cpp`, `-java`, `-js`, `-php`, `-ts` [10]. Row counts and quality are **UNVERIFIED**: the collection page shows unlabeled numbers. The contributing guide lists Kotlin, Scala and Swift as wanted languages and "Especially non-Python repos" as p1 [17].
- **Overlap with CooperBench repos (from profiles):** SWE-smith already has profiles for `pallets/click`, `pallets/jinja`, `stanfordnlp/dspy`, `go-chi/chi`, `react-hook-form/react-hook-form` [19, grep of `swesmith/profiles`]. Their `commit` values are SWE-smith's own pinned commits; we did not compare them with CooperBench's base commits (**UNVERIFIED**, likely different). **Inference:** to build bundles on CooperBench's exact snapshots we would have to add our own `RepoProfile` at CooperBench's base commit, which the contributing guide describes ("Each `RepoProfile` class corresponds to a unique GitHub repository + commit combination") [17].

## 5. Relevance to parallel-task bundles

### 5.1 What SWE-smith already gives us (facts)

1. **Many tasks on one snapshot.** Tasks from one repo share one environment [8, §2.2], and a `RepoProfile` is one repo + one commit [17]. Every instance of that repo is that commit plus a bug patch (instance branch, `base commit` field) [8 A.1; 6]. So independent bugs of the same repo are, by construction, patches against the same clean tree.
2. **Combining bugs exists, but it is not a controllable-overlap tool.**
   - `combine.same_file` groups bug patches by source file (it walks the per-file folder under `logs/bug_gen/<repo>/`) and calls `get_combos(patch_files, num_patches, max_combos)` [12]. `get_combos` is plain `itertools.combinations` truncated at `max_combos`, so it takes the first combinations in directory order, not a random or overlap-aware sample [14].
   - `apply_patches` applies the chosen patches one by one with `git apply`, takes the resulting diff, checks that it re-applies, and returns `None` on any failure [14]. The paper adds: "Merging patches occasionally fails if there is an overlapping conflict between two files, akin to a merge conflict with git; this usually happens when a function is declared within another" [8, §B.3].
   - After a success, all remaining combos that reuse any patch from the successful combo are dropped, so each function-level bug is used once [12; 8 §B.3].
   - Paper defaults: `num_bugs` in [2,4], `limit_per_file`=3, `max_combos`=40 for files; `num_bugs` in [2,5], `limit_per_module`=10, `max_combos`=100, `depth`=2 for modules [8, §B.3]. The docs examples use different numbers (e.g. 3/15/100) [4].
   - Module mode: "A depth of `2` means any patches under `a/b` are considered to be in the same module" [4]; "yield decreases significantly for every increased level of depth" [8, B.3].
   - Combined bugs are **re-validated as a single bug** [8, B.3], and the combined instance has its own F2P set. Yield 96.9% [8, Table 1].
   - The combination is **file-level or module-level only**. We found no option for "same function" or "different files across the repo" in the CLI [12, 13].
3. **Where bug locations are recorded.**
   - The `.diff` contains file paths and hunk line numbers (standard unified diff). **Inference:** this is our best source for exact file and line ranges.
   - The artifact directory is `logs/bug_gen/<repo>/<file path with / replaced by __>/<function name>_<signature hash8>/` [4; 14 `get_bug_directory`]. So file and function name are in the path.
   - `metadata__*.json` for single-entity bugs holds only `cost`, `explanation`, `output`, `rewrite`, `strategy` (`BugRewrite.to_dict()` in `swesmith/constants.py`) [18]; combine metadata holds `patch_files` and `num_patch_files` [12]. **Neither records file or line range.** The task instance JSON also has no file/function field [6, 9]. So we must derive location from `patch` ourselves (e.g. with the `unidiff` package, which SWE-smith itself imports in `same_module.py` [13]).
4. **Tests are existing repo tests and are visible.** "All FAIL TO PASS bugs are visible and runnable in the repository" [8, A.1]. There is no hidden test patch.
5. **Each instance's F2P/P2P was computed with only that bug applied** [6, 21]. Nothing in the docs says anything about applying several unrelated instances' patches at once and what happens to the tests (**UNVERIFIED**; the combine strategies re-validate the combined patch, which is the only multi-bug evidence [8, B.3]).

### 5.2 OUR PROPOSAL (inference, not from SWE-smith): bundles with a conflict-density dial

Goal: k bugs, all applied to one clean snapshot, one task per bug; we control how many of the k tasks touch the same file or function.

**Definitions (our vocabulary).** Pool = repo at one commit with SWE-smith's validated single-bug instances `B = {b_i}`. Task = one bug `b_i` with F2P tests `F_i` (these play the role of hidden tests, although SWE-smith makes them visible; see pitfalls). Bundle = k bugs.

**Step 0: choose pools.** Start with Python repos that SWE-smith already supports and that overlap CooperBench (jinja, click, dspy) so the two datasets can be compared; add chi (Go) via `SWE-smith-go` as a stretch [19, 10].

**Step 1: get single-entity bugs.** Either download from HF (`SWE-bench/SWE-smith`, or `SWE-smith-py`/`-go`) and keep only instances whose `instance_id` strategy is a single-entity one (`lm_modify`, `lm_rewrite`, `func_pm_*`; skip `combine_*` and `pr_mirror`) [9; 4], or generate our own with `procedural.generate` (free, no API key needed, per Table 1 cost 0.00 cents [8]). Pull the image with `download_images` or `create_images -r <repo>` [5].

**Step 2: index bug locations.** For each instance, parse `patch` with `unidiff` to get `(file, [line ranges])`, and map the line ranges to the enclosing function using the same entity extractor SWE-smith uses (`rp.extract_entities()` returns entities with `file_path`, `line_start`, `line_end` [16, 18]) on the clean tree. Store `{id, files, functions, line ranges, F2P}`. Also store the test files that hold each `F_i`.

**Step 3: define the dial.** For a bundle of k bugs, let `d` = fraction of task pairs that touch the same location. Levels:
- **L0, disjoint:** all k bugs in different files (and ideally different modules, i.e. different second-level directories, so we also avoid import coupling).
- **L1, same file, different functions:** groups of bugs in one file, no two in the same function and no overlapping line ranges.
- **L2, same function:** two or more bugs inside one function (non-overlapping lines). This is the hardest to get from SWE-smith, since combine never targets a function twice; we must pick two independently generated bugs for the same entity (different modifiers, e.g. `func_pm_op_change` + `func_pm_remove_cond`) and confirm `git apply` works for both.
- Mixed levels: pick `m` of the k bugs to share a file/function and the rest disjoint, so `d` can vary continuously (e.g. k=4, d in {0, 1/6, 3/6, 6/6}).

**Step 4: select and check a bundle.** Sample k bugs matching the level. Then, on a fresh checkout of the base commit:
1. `git apply --check` each patch alone, then apply all k in sequence (`git apply`, same approach as `apply_patches` [14]). Reject the bundle if any patch fails. Also reject if two patches have overlapping line ranges, since then reverting one can change the context of the other (**Inference**).
2. Run the repo test suite on the combined buggy tree (use `rp.test_cmd` and `rp.log_parser`, like `swesmith.harness.valid` [16, 21]). Require that each `F_i` still **fails** on the combined tree (so the bug is observable) and that `F_i` is not a test that also fails because of another bug's patch alone (compute `F_i` ∩ `F_j` over the k instances; keep bundles with small or zero overlap, or record the overlap as "shared test coupling" metric).
3. Run the gold reverse patch for **each subset** to confirm that undoing bug `i` makes exactly `F_i` pass (up to tests shared with other bugs). The full gold (revert all k) must restore the original `PASS_TO_PASS` set. This is our analogue of `combined.patch`.
4. Run the whole thing 2 times to drop flaky tests (SWE-smith does not describe flakiness handling for us; **UNVERIFIED**).

**Step 5: build the task instance for our pipeline.** Starting snapshot = base commit + all k bug patches (a single `bundle.patch`, or a git branch). Per-task prompt = that bug's `problem_statement` (generated by `swesmith.issue_gen.generate` [7]; one issue per bug so agents see k separate issues). Per-task grader tests = `F_i`. Use the shared `PASS_TO_PASS` as a regression set.

**Step 6: grade with our existing flow.** Our CooperBench-style grader applies the final tree diff against `BASE_SHA` and runs one `tests.patch` per feature, passing when `exit_code == 0 and parsed_passed > 0` [23 §2]. For SWE-smith bundles the "base" is the *buggy* snapshot and the tests already exist, so the adaptation is: (a) `BASE_SHA` := bundle snapshot (clean commit + bundle.patch); (b) skip `tests.patch` (no hidden tests exist), or pass the F2P test IDs/files and run them with the profile's `test_cmd`; (c) instead of a pass/fail exit code per test file, parse per-test statuses with the profile's `log_parser` and mark task i resolved iff **all `F_i` pass**, and report regression if any `PASS_TO_PASS` test fails (SWE-bench-style rule, [6]). Everything downstream (tokens, time, conflict rate, wasted work) stays the same. Merge conflict measurement for strategy "parallel agents + merge" is unchanged: each agent fixes its own task, we merge diffs.

**Step 7: what the dial measures (our expectation).** At L0 the k reverse-patches touch disjoint files, so merges should be clean and parallel strategies should win; at L2 the reverse patches share hunks, so naive merges should conflict. **Inference:** this is the clean, controlled contrast CooperBench cannot give (76.5% of CooperBench gold pairs conflict [23 §1]).

### 5.3 Pitfalls

- **Visible tests.** The F2P tests live in the repo, so agents can read and run them (the paper says so [8, A.1]). Either accept that (it is how SWE-smith tasks work), or strip/rename the F2P test files in the agent's snapshot and restore them at grading time (**Inference**; our grader already filters agent-written test files [23 §2]).
- **Bugs that cancel or interact.** Two bugs in one function can mask each other (a double sign flip), so F2P of the combined tree differs from the union. We validate on the combined tree (Step 4). The paper itself notes patches can fail to merge if "a function is declared within another" [8, B.3].
- **Shared tests / test coupling.** A test in `F_i` may fail because of bug j. Then task i cannot be solved without fixing j. We measure `F_i` ∩ `F_j` and either reject or keep with a "coupling" flag. SWE-smith has no mechanism for this (**UNVERIFIED** beyond what we read).
- **Flaky tests and timeouts.** Validation drops candidates whose test run exceeds the time limit (2 minutes in the paper; profile default `timeout`=90 s [8, §2.1; 16]). Running 4 bugs in the same run may need a longer limit. Pre-existing flaky tests are not described (**UNVERIFIED**).
- **Different test commands per repo.** Each profile has its own `test_cmd` and `log_parser` [16]; TypeScript uses `pnpm test` [19]. Reuse them rather than inventing our own.
- **Weak, templated issue text.** Static or test-derived statements are cheaper but less informative; LM issues cost ~2.54 cents each [7, 8]. For an agent benchmark we recommend LM-written issues (**Inference**).
- **Synthetic realism.** Procedural bugs are small (median 5 lines [8, Table 1]); a harness could solve them without coordination. L2 bundles may be easier than real features (**Inference**). Combined and LM bugs are somewhat larger [8, Table 12].
- **Environment mismatch.** SWE-smith pins its own commit per repo [19]; CooperBench pins other commits. Do not mix the two datasets on one image.
- **Compute.** Applying k patches and running a full suite per candidate bundle is cheap per bundle for small repos but the suite runs dominate (pandas-scale repos are heavy). Limit to small repos; cache the baseline run once per pool (**Inference**).
- **Platform.** SWE-smith docs only support Ubuntu with Docker [1]; our Mac needs amd64 emulation or a Linux/GPU box (**Inference**).

## 6. Legal and practical

- **License.** Repo: MIT (`LICENSE`, "Copyright (c) 2025 John Yang") [22]. HF dataset: MIT [9]. Paper A.2: repositories were chosen with licences "that allow non-proprietary use"; most are BSD/MIT/Apache, "the remainder are largely protective licenses (GPL)" [8]. Per-repo licences are in paper Table 6 (not read). **Inference:** each bug dataset item embeds code from its source repo, so the source repo's license applies to any redistributed snapshot.
- **API keys / models.**
  - Procedural bugs: no LM needed (cost 0.00 cents [8]).
  - LM Modify / Rewrite / PR Mirror / issue generation: LM calls via a litellm-style `--model` string. Examples in docs: `openai/gpt-4o`, `anthropic/claude-3-7-sonnet-20250219`, `openai/o3-mini` [4, 7]. Which environment variable is read: UNVERIFIED (we did not trace it).
  - Mirror creation needs GitHub access (`ORG_NAME_GH`, `--org`) [5]; `swesmith/profiles/base.py` also handles GitHub tokens and SSH keys for private repos [16].
  - Reference prices: $1,000 for all bug generation, $200 for 10K issues [8, §2.2].
- **Docker/compute.** Docker is required; Ubuntu 22.04 tested; no Windows/macOS support [1]. Test-suite time limit per instance 2 min (paper) [8]. `get_container` caps memory at 10 GB [16].
- **Prebuilt artefacts.**
  - Datasets: `SWE-bench/SWE-smith` (278 MB, MIT), per-language `SWE-bench/SWE-smith-{py,go,rs,cpp,java,js,php,ts}` [9, 10].
  - Trajectories `SWE-bench/SWE-smith-trajectories`, models `SWE-bench/SWE-agent-LM-32B` and `-7B`, `SWE-bench/SWE-Rater-32B` [1, 3].
  - Docker images: Docker Hub org `swebench`, name pattern above [16, 18]; also `github.com/SWE-bench/SWE-smith-envs` [1]. Per-image sizes: **UNVERIFIED** (the paper reports a total of 295 GB for 128 repos).

## 7. Limitations and risks

- **Authors state:** pipeline is Python-centric (paper); only fine-tuning was explored, not RL [8, Discussion]. Yield is limited by lack of test coverage or by candidates that "did not actually introduce relevant issues" [8, §2.2]. LM Rewrite is "not explicitly asked for bugs" [8, §2.2].
- **Authors state (design):** no hidden tests, F2P tests are visible [8, A.1]. Issue text quality "can significantly alter the difficulty and feasibility"; they tried several approaches (§D) and found LM-generated text the best proxy for real issues [8, §2.1; 7].
- **Dataset notes:** the maintainers state no further updates to the main HF dataset and point to language-specific sets [9]. Count mismatches (59.1k rows vs 50,137; 222 vs 128 repos) are visible on the card [9].
- **From the repo (verifiable):** docs reference `scripts/bug_gen.py` but the file is `scripts/bug_gen_modal.py`; the PR-mirror artifact section is empty; docs command `swesmith.build_repo.create_images` and mirror creation depend on a GitHub organisation (`swesmith`) we do not control [4, 5, repo listing].
- **For our use (Inference):** (1) bugs are small and local, so they may not reproduce the cross-file coordination of real features; (2) conflicts will be defined by us via patch hunks, not by task semantics; (3) correctness of F2P on a combined tree is not guaranteed and must be re-validated (Step 4); (4) any claim about task difficulty at k>1 is ours.

## 8. Map onto our vocabulary

| Ours | SWE-smith equivalent |
|---|---|
| repo | `RepoProfile` (`owner/repo`) |
| pool (repo at one base commit) | one `RepoProfile` = repo + `commit`; the Docker image `swebench/swesmith.<arch>.<owner>_1776_<repo>.<commit8>` [16] |
| task | one validated bug instance (`instance_id`, `patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `problem_statement`) |
| hidden tests | none; use `FAIL_TO_PASS` (existing tests) |
| gold patch | the reverse of `patch` (A.1 [8]) |
| bundle | our own: k bugs applied together (SWE-smith's `combine_*` instances are a different thing: one instance with several function-level bugs and one problem statement) |
| conflict density | our own metric computed from patch hunks (Step 3) |

## Report text

SWE-smith is an open-source toolkit (MIT license) from Yang et al. that turns a GitHub repository into an execution environment and then synthesises many task instances inside it; each instance is a bug patch that breaks one or more previously passing tests, and it carries FAIL_TO_PASS and PASS_TO_PASS test lists, an LM-written problem statement and the repository's shared Docker image. The authors report a dataset of about 50k instances from 128 Python repositories, built with procedural AST edits, LM modification or rewriting of functions, reverted pull requests and combinations of validated bugs from the same file or module. Because every instance of a repository is a patch on one pinned commit, many tasks can be placed on a single snapshot. As future work we plan to select k single-function bugs from one repository, group them by whether they touch different files, the same file or the same function, apply all k patches to the clean tree, and let each harness repair them, grading every task on its own FAIL_TO_PASS tests; the share of task pairs that overlap becomes an adjustable conflict-density dial. We still need to verify that bundles of independently validated bugs keep their individual F2P sets when applied together, that the visible tests do not leak solutions, whether SWE-smith's pinned commits match our pools, and how well the newer non-Python datasets work.

BibTeX (from the arXiv record [8] and the repository's own citation entry [1]; the venue claim "NeurIPS 2025 Datasets and Benchmarks Track, Spotlight" comes from the repo README and is not shown on the arXiv page, so it is UNVERIFIED independently):

```bibtex
@inproceedings{yang2025swesmith,
  title     = {{SWE-smith}: Scaling Data for Software Engineering Agents},
  author    = {Yang, John and Lieret, Kilian and Jimenez, Carlos E. and Wettig, Alexander and Khandpur, Kabir and Zhang, Yanzhe and Hui, Binyuan and Press, Ofir and Schmidt, Ludwig and Yang, Diyi},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS), Datasets and Benchmarks Track},
  year      = {2025},
  eprint    = {2504.21798},
  archivePrefix = {arXiv},
  primaryClass  = {cs.SE},
  url       = {https://arxiv.org/abs/2504.21798}
}

@misc{swesmith_repo,
  title        = {{SWE-smith}},
  author       = {{SWE-bench contributors}},
  howpublished = {\url{https://github.com/SWE-bench/SWE-smith}},
  note         = {MIT license; accessed 2026-11-06}
}
```

## Sources

1. `README.md`, https://github.com/SWE-bench/SWE-smith (clone at `9b74ac0`, read 2026-11-06): NeurIPS note, toolkit description, Ubuntu/Docker note, HF resources, citation block, directory listings (`swesmith/bug_gen/adapters/`, `swesmith/profiles/`, `scripts/`, `configs/`).
2. `docs/getting_started/quickstart.md` (https://swesmith.com/getting_started/quickstart/): script sequence.
3. `docs/getting_started/assets.md` (https://swesmith.com/getting_started/assets/): environments, dataset, model assets.
4. `docs/guides/create_instances.md` (https://swesmith.com/guides/create_instances/): strategies, commands, combine knobs, Modal script.
5. `docs/guides/env_construction.md` (https://swesmith.com/guides/env_construction/): `create_images`, `download_images`.
6. `docs/guides/harnesses.md` (https://swesmith.com/guides/harnesses/): validation, gather, evaluation, instance JSON.
7. `docs/guides/issue_gen.md` (https://swesmith.com/guides/issue_gen/): issue generation commands and alternatives.
8. Yang et al., "SWE-smith: Scaling Data for Software Engineering Agents", arXiv:2504.21798, https://arxiv.org/abs/2504.21798 (v1 30 Apr 2025, v2 21 May 2025); PDF https://arxiv.org/pdf/2504.21798 read as text: §2.1, §2.2, Tables 1-3, §3, Discussion, App. A.1-A.3, B.1-B.4, C, Tables 8 and 12.
9. https://huggingface.co/datasets/SWE-bench/SWE-smith (dataset card).
10. https://huggingface.co/collections/SWE-bench/swe-smith (per-language dataset names).
11. https://swesmith.com/ (homepage; "Expand to non-Python repositories").
12. `swesmith/bug_gen/combine/same_file.py`.
13. `swesmith/bug_gen/combine/same_module.py`.
14. `swesmith/bug_gen/utils.py` (`apply_patches`, `get_combos`, `get_bug_directory`, `get_patch`).
15. `swesmith/bug_gen/procedural/generate.py` and `swesmith/bug_gen/procedural/base.py`.
16. `swesmith/profiles/base.py` (`RepoProfile`, `image_name`, `get_container`, `get_test_cmd`, timeouts).
17. `CONTRIBUTING.md` (new languages, new repositories, `RepoProfile`).
18. `swesmith/constants.py` (`BugRewrite`, `CodeEntity`, `ORG_NAME_DH`, `ORG_NAME_GH`).
19. `swesmith/profiles/python.py`, `golang.py`, `typescript.py` (pallets click/jinja, stanfordnlp/dspy, go-chi/chi, react-hook-form profiles, `python_version`, `test_cmd`).
20. `configs/bug_gen/README.md`, `configs/bug_gen/lm_modify.yml`.
21. `swesmith/harness/valid.py`.
22. `LICENSE`.
23. Our docs: `docs/Phase1_Proposal.md` (dataset construction, conflict-density dial) and `docs/cooperbench_guide.md` (§1 gold conflicts, §2 grader).
