# Analysis: OpenCode + Qwen2.5-7B-Instruct on CooperBench `core` (Python pools)

Status: partial, 2026-11-06. Runs are still finishing; numbers below are from the runs on disk at the time of writing
(default prompt: 31 run records, `small_model` prompt: 21). Classification is by grepping grading logs, so it is approximate.
Scripts: the counts come from the run records (`agents/*/tool_calls.jsonl`, `patch.diff`, `grading/*.json` and their logs).

## Headline

**Every graded feature failed: 0 passes under S0, S1 and S2 (including all three S2 merge modes), with both prompts.**
Per-strategy pass rate is 0.00 with a 95% CI up to about 0.15 to 0.28 (n = 5 to 11 bundles). So this model cannot rank the
strategies on success. It can only be compared on time, tokens, merge conflicts and behaviour. A stronger model is needed
for a real strategy comparison (see "Next").

## Did the model actually attempt the tasks?

Yes. Of the agent runs, only a few ended with an empty patch (default prompt: S0 1 of 22, S1 3 of 11, S2 1 of 22; small prompt: S0 3 of 14,
S1 2 of 7, S2 3 of 14). Most patches touch Python source files, with tens to hundreds of tool calls and edits. The failures are
**bad code, not no attempt**.

## Why graded features fail

Share of graded feature results by cause (own/final/merge-mode results pooled per strategy; counts from the run logs):

| prompt | strategy | graded | syntax error | import / name error | assertion fail |
|---|---|---|---|---|---|
| default | S0 | 22 | 8 | 10 | 4 |
| default | S1 | 22 | 5 | 6 | 11 |
| default | S2 (own) | 18 | 8 | 6 | 4 |
| small_model | S0 | 14 | 7 | 3 | 4 |
| small_model | S1 | 14 | 3 | 2 | 9 |
| small_model | S2 (own) | 14 | 7 | 4 | 3 |

- Most failures are broken code (syntax or import errors) rather than a wrong-but-valid implementation.
  Seen in the logs: a blanket rename of `encode` in tiktoken, truncated or mis-indented edits, and imports of names that do not exist.
- S1 (one agent, all features) reaches real assertion failures more often (11 of 22 under the default prompt) than S0 or S2.
  A plausible reading is that the shorter single session leaves the code importable more often. This is a hypothesis, not tested.
- Merging does not rescue S2: naive, union and LLM-resolver merges give 0 passes. Syntax-error counts after the merge are equal
  or higher than for the agents' own patches (for example S2 default: own 8, union 12). Merge conflict rate is about 0.40 to 0.44 of bundles.

## Behaviour (from tool-call logs)

| | default prompt | `small_model` prompt |
|---|---|---|
| git commands (S0/S1/S2) | 20 / 122 / 11 | 0 / 0 / 0 |
| scratch-file style commands (touch, mkdir, echo >) | 366 / 177 / 284 | 2 / 0 / 0 |
| edits | 86 / 12 / 114 | 176 / 125 / 74 |
| test runs | 49 / 2 / 50 | 110 / 0 / 53 |
| invalid tool calls (of all calls) | about 5% | about 6 to 17% |

- With the default prompt the model wanders: it creates git branches, tries to commit and push, and touches files, instead of editing.
  The S1 default run spends 122 git calls for 12 edits.
- The `small_model` prompt removes the wandering (git and scratch commands drop to about zero) and multiplies real edits, but
  **does not change the pass rate (still 0)**. It increases tokens and time (S1 median 171 s vs 98 s, S0 875 s vs 588 s) because the agent now works longer.
- Invalid or malformed tool calls remain a steady source of wasted turns (about 5% default, up to 17% for S2 with the small prompt).

## Cost / time (medians, default prompt, 7B on one RTX 5000 Ada)

S1 98 s and 49K tokens; S0 588 s and 298K tokens; S2 483 s and 475K tokens. S2 parallelism is about 1.3 (up to 1.7 with the small prompt).
All of this is a local model, so dollar cost is not meaningful here.

## Caveats

- Arm 1 included duplicate bundles in reversed feature order (the bundle shuffle changed when a pool was added); they are extra samples, not independent bundles.
- Two default-prompt S2 runs failed outright on llama_index, because an agent's own patch did not apply to the base. This is a model failure, not a pipeline bug.
- Failure classification uses text matching on pytest logs and may mislabel some cases.
- Python pools only (7 of the 10 `core` pools); Go, TypeScript and Rust pools need toolchains that are not set up.

## Next

Run Qwen3.8-27B (INT4) on one bundle (click task2800) with S1, S0 and S2 and the `small_model` prompt. If it passes at all, the strategy
comparison becomes meaningful and can be extended to more pools. Until then the report can state: 7B is below the capability needed
(0 of about 100 graded features), time and token costs per strategy, S2 conflict rate, and the effect of the prompt on behaviour.
