| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.79 (0.52-0.92) | 0.57 | 1.00 |  | 0.122 | 2,319,343 | 2687 | 1.00 | 1 |
| S1 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.86 (0.60-0.96) | 0.71 | 1.09 |  | 0.139 | 1,330,508 | 1633 | 1.00 | 1 |
| S2 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.71 (0.45-0.88) | 0.57 | 0.91 | 0.29 | 0.318 | 3,410,087 | 2054 | 1.49 | 1 |
| S3 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.64 (0.39-0.84) | 0.29 | 0.82 |  | 0.141 | 2,622,308 | 4144 | 1.00 | 8 |
| S3@oracle | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.86 (0.60-0.96) | 0.71 | 1.09 |  | 0.126 | 1,962,555 | 2169 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.71 (0.45-0.88) | 0.57 | 0.91 |  | 0.116 | 1,538,291 | 2065 | 1.00 | 0 |

S3 planning (planner runs; recall/precision of predicted vs gold files; clash found = the planner saw that tasks share a file):

| strategy | model | n | valid plan | JSON nudge needed | file recall | file precision | clash found | split plans (>1 group) | executed |
|---|---|---|---|---|---|---|---|---|---|
| S3 | qwen3.8-27b-fp8-vllm | 7 | 4/7 | 0 | 1.00 | 0.94 | 1.00 | 0 | 7 |

Token source (docs/metrics_tokens.md): proxy 42 runs
