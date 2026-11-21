# S3 planner rules

S3 = **plan, then schedule**. A planner agent reads the k tasks of a bundle and predicts which files each task will change. Our code then turns that prediction into a schedule: tasks that share a file run one after another, the rest run in parallel.

The planner only **predicts**. It does not write code and does not build the schedule. This keeps its job small and lets us score it (file recall, file precision, conflict prediction; see `research/Task4_Metrics.md`).

## Rules for the planner agent (put these in its prompt)

1. **Do not edit anything.** Read the code and search it. Do not write files, run git, or change the repository.
2. **No web, no hidden tests.** Use only the repository and the task texts.
3. **For each task, list the source files it will change.** Use repository paths that exist, or mark a file as `new`. Also list the functions or classes you expect to change in each file.
4. **Include shared "glue" files.** If a task must register, export or configure something (for example `__init__.py`, a registry, a settings file, a router), list that file too. These are the files most likely to clash.
5. **Do not list test files or docs.** Agent-written tests are removed before grading, so they do not matter for conflicts.
6. **When unsure, include the file.** A missed shared file causes a merge conflict; an extra file only costs some parallelism. Prefer recall over precision.
7. **Give a confidence for each file**: `high` (the task text or code clearly needs it) or `low` (a guess).
8. **Check the code, do not guess from names.** Open the file or grep for the symbol before listing it.
9. **Stay within budget.** At most N tool calls (same step limit as the other strategies). If the budget runs out, return your best answer anyway.
10. **Return only the JSON below.** No extra text, no questions.

```json
{
  "tasks": [
    {"id": "f1", "files": [
      {"path": "src/pkg/core.py", "functions": ["parse", "Parser.run"], "confidence": "high"},
      {"path": "src/pkg/__init__.py", "functions": [], "confidence": "low"}
    ]},
    {"id": "f2", "files": [ ... ]}
  ]
}
```

## Rules for the scheduler (our code, not the agent)

1. **Two tasks clash** if their predicted file lists share at least one file (any confidence). Clashing tasks go in the same group.
2. **Groups are connected components**: if A clashes with B and B with C, then A, B and C form one group.
3. **Inside a group, run tasks one after another**, in the bundle's seeded order (the same order S1 uses). Each task starts from the tree the previous task left.
4. **Different groups run in parallel**, each in its own copy of the repository. Merge their results with the S2 merge modes (naive, union, LLM).
5. **If the planner fails** (bad JSON, no answer, unknown task ids), fall back to S1 (everything sequential) and mark the run so it is reported separately.
6. **Log everything**: the raw plan, the groups, and per-task file lists, so file recall and conflict prediction can be computed later against the gold patches.

## Fairness

- **Same model** for planner and coding agents. Planner tokens and time count toward the S3 total.
- **Same task text and step limit** as in S0, S1 and S2. Harness subagents are off.
- **The coding agents get their normal prompt.** They are not told about the plan, so only the scheduling changes. (Telling them is a separate variant, not plain S3.)

## Optional variants (only after plain S3 works)

- **Function-level clash:** tasks that share a file but no function run in parallel. Saves time but risks more conflicts.
- **Change notes:** in a sequential group, tell the next agent in 2–3 lines what the previous one changed (like P3).
- **Oracle plan:** use the gold patch files instead of predictions. This is the upper bound for S3 and shows how much is lost by predicting.
