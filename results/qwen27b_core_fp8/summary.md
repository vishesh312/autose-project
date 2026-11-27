| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.70 (0.40-0.89) | 0.40 | 1.00 |  | 0.228 | 3,671,483 | 3162 | 1.00 | 1 |
| S1 | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.80 (0.49-0.94) | 0.60 | 1.14 |  | 0.139 | 1,330,508 | 1633 | 1.00 | 1 |
| S2 | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.60 (0.31-0.83) | 0.40 | 0.86 | 0.20 | 0.318 | 3,410,087 | 2054 | 1.54 | 1 |
| S3 | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.50 (0.24-0.76) | 0.00 | 0.71 |  | 0.290 | 2,709,909 | 4782 | 1.00 | 6 |
| S3@oracle | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.80 (0.49-0.94) | 0.60 | 1.14 |  | 0.174 | 1,962,555 | 2169 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-fp8-vllm | 2 | 5 | 0.60 (0.31-0.83) | 0.40 | 0.86 |  | 0.165 | 1,538,291 | 2065 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 30 runs
