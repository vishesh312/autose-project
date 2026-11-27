| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-fp8-vllm | 2 | 2 | 0.75 (0.30-0.95) | 0.50 | 1.00 |  | 0.218 | 2,371,502 | 2393 | 1.00 | 0 |
| S1 | opencode | qwen3.8-27b-fp8-vllm | 2 | 1 | 0.50 (0.09-0.91) | 0.00 | 1.00 |  | 0.139 | 1,330,508 | 1633 | 1.00 | 0 |
| S2 | opencode | qwen3.8-27b-fp8-vllm | 2 | 1 | 0.50 (0.09-0.91) | 0.00 | 1.00 | 0.00 | 0.355 | 3,410,087 | 2054 | 1.96 | 0 |
| S3 | opencode | qwen3.8-27b-fp8-vllm | 2 | 1 | 0.50 (0.09-0.91) | 0.00 | 1.00 |  | 0.290 | 2,709,909 | 4782 | 1.00 | 1 |
| S3@oracle | opencode | qwen3.8-27b-fp8-vllm | 2 | 1 | 0.50 (0.09-0.91) | 0.00 | 1.00 |  | 0.174 | 1,662,432 | 2138 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-fp8-vllm | 2 | 1 | 0.50 (0.09-0.91) | 0.00 | 1.00 |  | 0.093 | 886,094 | 1380 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 7 runs
