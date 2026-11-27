| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-fp8-vllm | 2 | 6 | 0.75 (0.47-0.91) | 0.50 | 1.00 |  | 0.175 | 2,995,413 | 2924 | 1.00 | 1 |
| S1 | opencode | qwen3.8-27b-fp8-vllm | 2 | 6 | 0.83 (0.55-0.95) | 0.67 | 1.11 |  | 0.143 | 2,081,866 | 1894 | 1.00 | 1 |
| S2 | opencode | qwen3.8-27b-fp8-vllm | 2 | 6 | 0.67 (0.39-0.86) | 0.50 | 0.89 | 0.33 | 0.355 | 4,433,232 | 2545 | 1.46 | 1 |
| S3 | opencode | qwen3.8-27b-fp8-vllm | 2 | 6 | 0.58 (0.32-0.81) | 0.17 | 0.78 |  | 0.215 | 2,666,108 | 4463 | 1.00 | 7 |
| S3@oracle | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.80 (0.49-0.94) | 0.60 | 1.14 |  | 0.174 | 1,962,555 | 2169 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-fp8-vllm | 2 | 6 | 0.67 (0.39-0.86) | 0.50 | 0.89 |  | 0.138 | 2,103,343 | 2151 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 35 runs
