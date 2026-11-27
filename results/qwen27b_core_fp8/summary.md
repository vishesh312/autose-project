| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.79 (0.52-0.92) | 0.57 | 1.00 |  | 0.122 | 2,319,343 | 2687 | 1.00 | 1 |
| S1 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.86 (0.60-0.96) | 0.71 | 1.09 |  | 0.139 | 1,330,508 | 1633 | 1.00 | 1 |
| S2 | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.71 (0.45-0.88) | 0.57 | 0.91 | 0.29 | 0.318 | 3,410,087 | 2054 | 1.49 | 1 |
| S3 | opencode | qwen3.8-27b-fp8-vllm | 2 | 6 | 0.58 (0.32-0.81) | 0.17 | 0.78 |  | 0.215 | 2,666,108 | 4463 | 1.00 | 7 |
| S3@oracle | opencode | qwen3.8-27b-fp8-vllm | 2 | 7 | 0.86 (0.60-0.96) | 0.71 | 1.09 |  | 0.126 | 1,962,555 | 2169 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-fp8-vllm | 2 | 6 | 0.67 (0.39-0.86) | 0.50 | 0.89 |  | 0.138 | 2,103,343 | 2151 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 40 runs
