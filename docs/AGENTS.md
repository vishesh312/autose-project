# AGENTS.md: docs

Read the root `AGENTS.md` first.

## Index

| File | What | Status |
|---|---|---|
| `Phase1_Proposal.md` | the submitted proposal: problem, scope, metrics | fixed (submitted) |
| `research/Task2_Models_Harnesses.md` | teammate's model + harness + hardware shortlist | **guidance only**; some claims corrected in `serving_models.md` |
| `research/Task4_Metrics.md` | metric definitions, k values, repeats and statistics, what to log | guidance; `parbench` implements most of it |
| `research/Task5_Strategies.md` | prior work and the strategies S0 to S4 and prompt changes P0 to P3 | guidance; S3 and P2/P3 not implemented yet |
| `cooperbench_guide.md` | how CooperBench's data and grader work, and how we use them for k>2 | verified by reading code at `63b9d44`, not by running it |
| `harnesses.md` | per-CLI install, headless command, JSON schema, resume, subagent switches, custom endpoints | each fact marked verified or UNVERIFIED |
| `serving_models.md` | serving open models on a Mac, NVIDIA GPUs and SLURM; which engine speaks which API | checked against local Ollama only |

## Rules for editing docs

- Keep the **verified / UNVERIFIED** marks honest. When you confirm something with a live run, change the mark and say how (command, date).
- Use our vocabulary (task, pool, bundle) and say which CooperBench word it maps to when it matters.
- Put dates on anything that goes stale (prices, leaderboard numbers, model availability).
- Link to files with relative paths. If you move a doc, fix the links (`grep -rn "<old name>" .`).
- Don't paste secrets, tokens or long raw logs. Summarise and point to `results/...`.
- New research notes go in `docs/research/`; things that describe *our* code or setup go directly in `docs/`.
