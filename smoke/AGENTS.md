# AGENTS.md: smoke

Read the root `AGENTS.md` first. This directory holds the **toy dataset** used to check the pipeline end to end in minutes, before spending time or money on real CooperBench pools.

## What's here

- `build_toy_dataset.py` generates `smoke/dataset/toy_task/task1/` in CooperBench layout: a tiny Python package `textkit` with six features and hidden tests, `combined.patch`, a `runner.sh` that follows CooperBench's grader contract, and a Dockerfile. It also writes `smoke/dataset/gold_conflict_report.json`.
- The image is `parbench-toy-textkit:task1` (named in the pool's `IMAGE` file, so `parbench` doesn't look for it on Docker Hub).

Regenerate and build:

```bash
python smoke/build_toy_dataset.py && parbench build-toy
parbench build-images --toy --harnesses opencode      # adds the agent CLIs
```

## Known conflict structure (this is the point of the toy pool)

| Features | Why | Gold patches |
|---|---|---|
| f1 `lines`, f2 `unique` | both add a function and an `OPERATIONS` entry at the same spot | **conflict** |
| f3 `--json`, f4 stdin | both edit the same lines of `cli.py` | **conflict** |
| f5 `slugify` | new file | independent |
| f6 punctuation-only words | edits `word_count`, far from f1/f2's hunk | clean |

Good bundles: `{f1,f2}` and `{f3,f4}` (conflicting pairs), `{f1,f5,f6}` (clean triple), `{f1,f2,f3,f4,f5,f6}` (k=6, mixed). The prompt files below are small enough for a 2B to 9B local model.

## Smoke prompts

`smoke/prompts/*.md` are standalone single-agent prompts for `parbench probe --prompt-file` (tool use, editing, running tests, asking questions, autonomy). They are for checking a harness + model, not for scoring.

## Rules

- Keep the toy pool deterministic: fixed commit date, no network at grading time.
- If you change a feature, regenerate the dataset and rebuild the image, then run `parbench check-gold --toy`: tests alone must fail, gold must pass, `combined.patch` must pass all six.
- Don't use toy results in the report. They only prove the plumbing.
