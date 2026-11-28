| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S3 | opencode | qwen3.8-27b-pi-vllm | 2 | 5 | 0.80 (0.49-0.94) | 0.60 |  |  | 0.012 | 237,586 | 231 | 1.00 | 0 |

S3 planning (planner runs; recall/precision of predicted vs gold files; clash found = the planner saw that tasks share a file):

| strategy | model | n | valid plan | JSON nudge needed | file recall | file precision | clash found | split plans (>1 group) | executed |
|---|---|---|---|---|---|---|---|---|---|
| S3 | qwen3.8-27b-pi-vllm | 5 | 5/5 | 0 | 1.00 | 1.00 | 1.00 | 0 | 5 |

Token source (docs/metrics_tokens.md): proxy 5 runs
