| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.75 (0.41-0.93) | 0.50 | 1.00 |  | 0.043 | 545,285 | 697 | 1.00 | 0 |
| S1 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.62 (0.31-0.86) | 0.25 | 0.83 |  | 0.040 | 426,852 | 487 | 1.00 | 0 |
| S2 | opencode | qwen3.8-27b-pi-vllm | 2 | 3 | 0.50 (0.19-0.81) | 0.00 | 0.75 | 0.33 | 0.097 | 935,285 | 904 | 1.17 | 0 |
| S3 | opencode | qwen3.8-27b-pi-vllm | 2 | 3 | 0.50 (0.19-0.81) | 0.00 | 0.75 |  | 0.041 | 394,481 | 379 | 1.00 | 3 |
| S3@oracle | opencode | qwen3.8-27b-pi-vllm | 2 | 3 | 0.50 (0.19-0.81) | 0.00 | 0.75 |  | 0.039 | 378,262 | 365 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-pi-vllm | 2 | 3 | 0.67 (0.30-0.90) | 0.33 | 1.00 |  | 0.068 | 648,171 | 411 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 20 runs
