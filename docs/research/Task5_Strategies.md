# Task 5: Strategies

**What we mean by a strategy:** how we give *k* tasks to the agents and combine their work. There are two kinds:
- **Workflow:** who works on which task, in what order, and how the code gets merged.
- **Prompt change:** a few extra lines added to the task text, such as "plan first".

*Task* and *bundle* mean the same as in [Task4_Metrics.md](Task4_Metrics.md).

## 1. What others have tried

### Research (2026)

| Source | What they tried | What they found |
|---|---|---|
| [CooperBench](https://arxiv.org/abs/2601.13295) (Jan) | 2 agents in parallel. Each sees only its own task and can message the other. Code merged with `git merge`, then "union" (keep both sides of a clash), then a small LLM | Two agents did about half as well as one agent doing both tasks. Messaging cut conflicts but not final success. Union did most of the rescue (GPT-5: 13.9% → 26.7%); the LLM added ~1 point. Agents that planned in their first message had fewer conflicts (29% vs 52%), but this was only observed, not tested |
| [ParallACT](https://arxiv.org/abs/2611.00314) (Oct) | One agent with both tasks, vs. hand-off (agent B starts from agent A's finished code), vs. parallel agents with or without messaging | One agent did best. On clashing pairs, Claude Code + Opus 4.8 fell from 62% to 16% when run in parallel. Knowing a peer exists didn't help; messaging helped a little, for extra tokens. With open models, hand-off solved 60% of clashing pairs (as many as one agent) vs. 19% in parallel, at about the same token cost |
| [NP-Bench](https://arxiv.org/abs/2610.07261) (Oct) | No coordination, vs. a warning when a clash happens, vs. a planner that gives each agent its own files and sets the merge order | The planner made all 9 scripted scenarios merge cleanly (vs. 1 of 9 with no coordination). But it was told each task's files; it didn't predict them |
| [Subagents study](https://arxiv.org/abs/2610.10263) (Oct) | Codex, Claude Code and Kimi Code with built-in subagents on vs. off | Success changed by −11.9 to +2.3 points, while tokens rose 1.4–3.3×. Gains came mainly on long tasks |
| [CAID](https://arxiv.org/abs/2603.21489) (Mar) | A manager plans. Each worker has its own git worktree, merges its own work and fixes its own conflicts. Tests check every merge | Beat a single agent on two repo-building benchmarks |
| [stale](https://arxiv.org/abs/2609.25396) (Sep) | Patches that pass alone but break once combined | A short note telling the agent what the other agent changed fixed 82% of these cases |
| [Merge-Bench](https://arxiv.org/abs/2605.25890) (May) | LLMs fixing real merge conflicts | The best models fix fewer than 60% |

### Tools and practice

| Source | What they do | Worth knowing |
|---|---|---|
| Claude Code ([subagents](https://code.claude.com/docs/en/sub-agents), [agent teams](https://code.claude.com/docs/en/agent-teams)) | Subagents can each work in their own git worktree. Agent teams share a task list and message each other | The docs say to give each teammate "a different set of files". Agent teams use about 7× more tokens ([costs](https://code.claude.com/docs/en/costs)) |
| [Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Cursor](https://cursor.com/docs/configuration/worktrees), [GitHub Copilot](https://docs.github.com/en/copilot/concepts/agent-capabilities/choosing-and-delegating-agent-work/delegating-and-parallelizing-work-with-agents) | One branch or worktree per task, each ending as a pull request that a person reviews | Codex and Cursor can also run one task several times and let you pick the best result (best-of-n) |
| [Cursor research](https://cursor.com/blog/scaling-agents) | Planner agents hand tasks to worker agents | File locks slowed 20 agents to the speed of 2–3. They dropped their separate merge agent: "Workers were already capable of handling conflicts themselves" |
| [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system), [Cognition](https://cognition.ai/blog/dont-build-multi-agents) | Essays on when to use several agents | Anthropic: multi-agent setups use about 15× the tokens of a chat, and "most coding tasks involve fewer truly parallelizable tasks than research". Cognition: parallel agents that write code make clashing choices. A [2026 follow-up](https://cognition.ai/blog/multi-agents-working) says it works when only one agent writes |

### What this tells us

- **One agent doing all the tasks is the bar to beat.** It was the strongest setup in both CooperBench and ParallACT. A parallel setup has to come close to it while being faster.
- **Most of the damage happens at merge time.** How we merge (union, or letting agents fix their own conflicts) matters as much as how we split the work.
- **Structure helps more than chat.** Separate files, a fixed merge order and notes about finished changes helped. Free messaging between agents helped little.

## 2. Strategies we will test

### Workflows

| ID | Name | How it works | Why |
|---|---|---|---|
| S0 | Isolated | Each task alone: a fresh agent on the original code | Baseline for retention (Task 4) |
| S1 | One agent | One agent gets all *k* tasks in one prompt and does them itself, one after another. No subagents | The strongest setup in CooperBench and ParallACT |
| S1b | Hand-off | A fresh agent for each task, one after another. Each starts from the previous agent's code | Matched one agent in ParallACT (open models), and each agent starts with a short, clean context |
| S2 | Parallel + merge | One agent per task, all at once, each in its own worktree. Then `git merge` → union → LLM resolver | The plain parallel setup, with the same merge steps as CooperBench |
| S2b | Parallel + self-fix | Like S2, but merge one task at a time. If a merge clashes or breaks tests, that task's agent gets the new code and fixes its own work | What CAID and Cursor do. The agent knows what its change was meant to do; a separate resolver doesn't |
| S3 | Plan, then schedule | A planner reads all tasks and predicts each one's files. Tasks that share files run one after another; the rest run in parallel | NP-Bench showed this works when the files are known. We test it with predicted files |
| S4 | Harness decides | All tasks in one prompt to a harness with its own subagents turned on. Only for harnesses that have subagents (e.g. OpenCode, oh-my-pi, Claude Code; not Pi) | How people actually use these tools. The subagents study suggests extra cost for mixed results |

### Prompt changes

Each change adds only a few lines to the task text. Short prompts did better than detailed ones in [a 2026 study](https://arxiv.org/abs/2603.09004).

| ID | Change | Used with | Why |
|---|---|---|---|
| P0 | None: plain task text | All | Default |
| P1 | **Plan first:** "Before editing, list the files and functions you will change." In S2, each agent's plan is shared with the others before anyone writes code | S1, S2 | CooperBench saw far fewer conflicts after first-message plans, but nobody has tested it directly |
| P2 | **Know the others:** each agent also gets the other tasks' descriptions, and is asked to change only what its own task needs | S2 | CooperBench agents saw only their own task. ParallACT found that knowing a peer *exists* doesn't help; knowing *what* the peers are doing might |
| P3 | **Change notes:** when a task is merged, agents still running get a 2–3 line note on what changed | S2 | In stale, such a note fixed 82% of broken combinations |

### Not planned for now

- **Free messaging between agents:** little or no gain in CooperBench and ParallACT, at extra token cost.
- **File locks:** they slowed Cursor's agents badly. S3 already gives each shared file to one task at a time.
- **Best-of-n, reviewer or supervisor agents:** these buy quality with extra compute, which is a different question. They may fit our own method later (Task 6).
- **A strong model plans, a weak model codes:** also a candidate for Task 6.

## 3. What to run first

1. **Pilot:** S0, S1 and S2, all with P0. This matches the pilot in [Task2_Models_Harnesses.md](Task2_Models_Harnesses.md).
2. **Next:** S2 + P1. It's cheap to add and tests the planning claim directly.
3. **Then:** S1b, S2b, S3 and S4, and finally P2 and P3.

Try prompt changes only on S2 (plus P1 on S1). Crossing every prompt with every workflow would multiply the number of runs.

## 4. Rules to keep it fair

- **Same model** for the agents, the planner and the resolver. Otherwise we'd be testing a stronger helper, not a strategy.
- **Same step limit** per agent. CooperBench used 100 actions.
- **Same task text** everywhere. Prompt changes only add a short block.
- **Same order:** pick one random task order per bundle, and use it for S1, S1b and the merge order in S2 and S2b.
- **No hidden subagents:** turn off a harness's own subagents in every strategy except S4.

## 5. What is new in our study

- CooperBench and ParallACT test pairs of tasks. We go up to *k* = 6.
- NP-Bench's planner was told each task's files. Our S3 has to predict them.
- We run the same strategies on several harnesses and models.
- We measure cost and time (Task 4), not only success.
