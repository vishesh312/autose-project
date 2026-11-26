| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-pi-vllm | 2 | 6 | 0.83 (0.55-0.95) | 0.67 | 1.00 |  | 0.054 | 770,725 | 866 | 1.00 | 0 |
| S1 | opencode | qwen3.8-27b-pi-vllm | 2 | 5 | 0.70 (0.40-0.89) | 0.40 | 0.87 |  | 0.073 | 696,428 | 787 | 1.00 | 0 |
| S2 | opencode | qwen3.8-27b-pi-vllm | 2 | 5 | 0.70 (0.40-0.89) | 0.40 | 0.87 | 0.40 | 0.097 | 935,285 | 910 | 1.11 | 0 |
| S3 | opencode | qwen3.8-27b-pi-vllm | 2 | 5 | 0.70 (0.40-0.89) | 0.40 | 0.87 |  | 0.041 | 613,448 | 846 | 1.00 | 5 |
| S3@oracle | opencode | qwen3.8-27b-pi-vllm | 2 | 5 | 0.70 (0.40-0.89) | 0.40 | 0.87 |  | 0.039 | 378,262 | 630 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-pi-vllm | 2 | 4 | 0.50 (0.22-0.78) | 0.25 | 0.67 |  | 0.068 | 430,422 | 384 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 30 runs
