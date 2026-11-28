| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

S3 planning (planner runs; recall/precision of predicted vs gold files; clash found = the planner saw that tasks share a file):

| strategy | model | n | valid plan | JSON nudge needed | file recall | file precision | clash found | split plans (>1 group) | executed |
|---|---|---|---|---|---|---|---|---|---|
| S3@planonly | qwen3.8-27b-pi-vllm | 21 | 21/21 | 0 | 1.00 | 0.96 | 1.00 | 0 | 0 |

Token source (docs/metrics_tokens.md): proxy 21 runs
