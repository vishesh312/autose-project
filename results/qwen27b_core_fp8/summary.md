| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-fp8-vllm | 2 | 3 | 0.67 (0.30-0.90) | 0.33 | 1.00 |  | 0.057 | 1,071,520 | 1625 | 1.00 | 1 |
| S1 | opencode | qwen3.8-27b-fp8-vllm | 2 | 2 | 0.75 (0.30-0.95) | 0.50 | 1.00 |  | 0.089 | 1,025,764 | 1423 | 1.00 | 0 |
| S2 | opencode | qwen3.8-27b-fp8-vllm | 2 | 2 | 0.75 (0.30-0.95) | 0.50 | 1.00 | 0.00 | 0.231 | 2,734,182 | 1998 | 1.65 | 0 |
| S3 | opencode | qwen3.8-27b-fp8-vllm | 2 | 2 | 0.50 (0.15-0.85) | 0.00 | 0.67 |  | 0.197 | 1,840,528 | 3168 | 1.00 | 2 |
| S3@oracle | opencode | qwen3.8-27b-fp8-vllm | 2 | 2 | 0.75 (0.30-0.95) | 0.50 | 1.00 |  | 0.129 | 1,631,586 | 2119 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-fp8-vllm | 2 | 2 | 0.75 (0.30-0.95) | 0.50 | 1.00 |  | 0.087 | 1,212,192 | 1723 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 13 runs
