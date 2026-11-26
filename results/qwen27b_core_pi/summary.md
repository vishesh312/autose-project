| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.75 (0.41-0.93) | 0.50 | 1.00 |  | 0.043 | 545,285 | 697 | 1.00 | 0 |
| S1 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.62 (0.31-0.86) | 0.25 | 0.83 |  | 0.040 | 426,852 | 487 | 1.00 | 0 |
| S2 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.62 (0.31-0.86) | 0.25 | 0.83 | 0.50 | 0.076 | 781,218 | 907 | 1.14 | 0 |
| S3 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.62 (0.31-0.86) | 0.25 | 0.83 |  | 0.036 | 503,964 | 613 | 1.00 | 4 |
| S3@oracle | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.62 (0.31-0.86) | 0.25 | 0.83 |  | 0.028 | 354,520 | 498 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.50 (0.22-0.78) | 0.25 | 0.67 |  | 0.068 | 430,422 | 384 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 24 runs
