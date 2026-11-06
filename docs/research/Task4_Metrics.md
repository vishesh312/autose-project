# Task 4: Metrics

**Words used below:**
- **Task:** one CooperBench feature, with its own tests.
- **Bundle:** *k* tasks from the same pool, meaning the same repo and starting commit.
- **Run:** one bundle × one strategy × one harness + model × one repeat.
- **Strategies:**
  - **S0 isolated:** each task on its own.
  - **S1 sequential:** one session does the tasks one after another.
  - **S2 naive fan-out:** one agent per task, in parallel, then an LLM merges the results.
  - **S3 predict-then-schedule:** a planner predicts which tasks clash, runs the clashing ones one after another and the rest in parallel.
  - **S4 harness-native:** the harness gets all the tasks at once and splits the work itself.
- **Gold patch:** CooperBench's reference solution for a task.

Every run ends with one final version of the code. We run every task's tests on it.

## 1. What we measure

### Correctness

| Metric | What it tells us | How to compute it |
|---|---|---|
| **Task pass rate** | How many tasks work at the end | tasks whose tests pass ÷ *k* |
| **Bundle success** | Did everything work? | 1 if all *k* tasks pass, else 0. For *k* = 2 this is CooperBench's success measure |
| **Retention** | How much we lose by doing tasks together | task pass rate (strategy) ÷ task pass rate (S0), on the same tasks. 1.0 means no loss |
| **Lost in merge** | Work that was done, then broken by the merge | tasks that pass in the agent's own copy of the repo but fail in the final code (S2–S4) |

### Conflicts (strategies that merge: S2–S4)

| Metric | What it tells us | How to compute it |
|---|---|---|
| **Conflict rate** | How often agents' changes clash | share of task pairs whose patches conflict under plain `git merge` |
| **Overlap** | How much agents edited the same code | lines of the original code changed by 2 or more agents |
| **Merge success** | How much the LLM resolver saves us | bundle success after plain `git merge`, and again after the resolver (CooperBench reports both) |

### Cost and waste

| Metric | What it tells us | How to compute it |
|---|---|---|
| **Tokens** | Total model use | input, cached input, output and reasoning tokens, summed over all agents, the planner and the resolver |
| **Cost ($)** | Money spent | tokens × one fixed price list (4 Nov 2026). For self-hosted models, use the OpenRouter price of the same model, and also report GPU-hours |
| **Cost per solved task** | The main efficiency number | total $ ÷ tasks that pass at the end |
| **Coordination overhead** | What planning and merging cost | planner + resolver tokens ÷ all tokens |
| **Wasted tokens** | Work thrown away | tokens used by agents whose task was lost in merge |
| **Repeated reading** | Agents exploring the same code twice | files read by more than one agent in the same bundle (from tool-call logs) |

We use one fixed price list because prices change over time and differ between providers. That keeps runs comparable.

### Time and parallelism

| Metric | What it tells us | How to compute it |
|---|---|---|
| **Wall-clock time** | How long the user waits | from the first model call to the final merged code. Includes planning and merging, not the final grading tests |
| **Agent-busy time** | Total work done | add up how long each agent (plus the planner and resolver) was running |
| **Effective parallelism** | How much really ran at the same time | agent-busy time ÷ wall-clock time. 1 means nothing overlapped; *k* means every agent ran fully in parallel |
| **Speedup** | Is parallel actually faster? | wall-clock time (S1) ÷ wall-clock time (strategy) |
| **Waiting time** | Time lost that isn't the strategy's fault | retries, rate-limit waits and server queueing. Report it separately |

### Planning quality (S3 only)

| Metric | What it tells us | How to compute it |
|---|---|---|
| **File recall** | Did the planner find the files each task needs? | gold-patch files the planner predicted ÷ all gold-patch files |
| **File precision** | Did it predict extra files? | predicted files that are in the gold patch ÷ all predicted files |
| **Conflict prediction** | Did it spot which pairs clash? | precision and recall over task pairs: predicted "will clash" vs. gold patches that conflict under `git merge` |

## 2. How many tasks in parallel (*k*)

- **Pilot:** *k* = 2, the same as CooperBench, so we can check our numbers against theirs. Also *k* = 3.
- **Main runs:** *k* = 2, 3, 4 and 6. S0 is the *k* = 1 baseline.
- **Why we don't go higher:**
  - Scores fall fast as *k* grows. In CooperBench's small test, success dropped from 68.6% with 2 agents to 46.5% with 3 and 30.0% with 4.
  - The pools limit *k*. In our file-overlap table ([autose_project.md](autose_project.md)), 28 of 30 pools have at least 4 features and 18 have at least 6, but only 10 have 8 or more.
- **Agents running at the same time:**
  - In S2, all *k* agents run at once. In S3 the planner decides how many; in S4 the harness decides.
  - Record how many agents were actually running at each moment. Effective parallelism (above) sums this up.
- **Keep timing fair:**
  - Runs that share a server or API key slow each other down. For time metrics, run one bundle at a time per server.
  - Runs that are only for pass rate and cost can run side by side.
  - On Ada, GPU memory limits how many agents one server can serve at once, so record `--max-num-seqs`.

## 3. Repeats and statistics

- **Repeats:** at least 3 per run, because Claude models can't be made fully repeatable.
- **Rates** (pass rate, conflict rate): report the mean with a 95% confidence interval. Use Wilson intervals, as CooperBench does.
- **Time and cost:** report the median and the 25th–75th percentile range. A few very long runs would distort the mean.
- **Compare strategies on the same bundles.** Then any difference comes from the strategy, not from some bundles being easier.
- **Break every metric down by *k*,** and later by conflict density (Task 3).

## 4. What to log

To compute the metrics above, we need to log:

- **Each model call:** agent ID, start and end time, the four token counts, cost, and retries.
- **Each tool call:** agent ID, tool name, and the files it read or edited.
- **Each agent:** its final patch, and its task's tests run on its own copy of the repo before the merge.
- **Merging:** the `git merge` result for each pair, which files and lines conflicted, and the resolver's tokens and output.
- **Final code:** the test result for every task.
- **Setup:** harness and version, model, quantization, server settings, strategy, *k*, and repeat number.

## 5. What to show first

In the report, lead with five numbers per strategy:

1. Task pass rate
2. Retention vs. S0
3. Cost per solved task
4. Speedup vs. S1
5. Conflict rate (plus conflict prediction for S3)

Add two plots:
- **Pass rate vs. *k*:** one line per strategy.
- **Cost vs. pass rate:** one point per strategy. The best strategies sit top-left, with high pass rates at low cost.
