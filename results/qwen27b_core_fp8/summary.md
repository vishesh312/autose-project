| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.70 (0.40-0.89) | 0.40 | 1.00 |  | 0.228 | 3,671,483 | 3162 | 1.00 | 1 |
| S1 | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.80 (0.49-0.94) | 0.60 | 1.14 |  | 0.139 | 1,330,508 | 1633 | 1.00 | 1 |
| S2 | opencode | qwen3.8-27b-fp8-vllm | 2 | 4 | 0.50 (0.22-0.78) | 0.25 | 0.80 | 0.25 | 0.355 | 2,734,182 | 1998 | 1.59 | 1 |
| S3 | opencode | qwen3.8-27b-fp8-vllm | 2 | 4 | 0.50 (0.22-0.78) | 0.00 | 0.80 |  | 0.215 | 2,017,626 | 3294 | 1.00 | 5 |
| S3@oracle | opencode | qwen3.8-27b-fp8-vllm | 2 | 4 | 0.75 (0.41-0.93) | 0.50 | 1.20 |  | 0.138 | 1,812,494 | 2154 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-fp8-vllm | 2 | 4 | 0.50 (0.22-0.78) | 0.25 | 0.80 |  | 0.093 | 1,212,192 | 1723 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 26 runs
