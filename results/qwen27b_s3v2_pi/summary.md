| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S3 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.88 (0.53-0.98) | 0.75 |  |  | 0.009 | 181,310 | 224 | 1.00 | 0 |

S3 planning (planner runs; recall/precision of predicted vs gold files; clash found = the planner saw that tasks share a file):

| strategy | model | n | valid plan | JSON nudge needed | file recall | file precision | clash found | split plans (>1 group) | executed |
|---|---|---|---|---|---|---|---|---|---|
| S3 | qwen3.8-27b-pi-vllm | 4 | 4/4 | 0 | 1.00 | 1.00 | 1.00 | 0 | 4 |

Token source (docs/metrics_tokens.md): proxy 4 runs
