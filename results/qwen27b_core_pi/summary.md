| strategy | harness | model | k | n | task pass (95% CI) | bundle succ | retention | conflict | $/solved | tokens (med) | wall s (med) | parallelism | nudges |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | opencode | qwen3.8-27b-pi-vllm | 2 | 6 | 0.83 (0.55-0.95) | 0.67 | 1.00 |  | 0.054 | 770,725 | 866 | 1.00 | 0 |
| S1 | opencode | qwen3.8-27b-pi-vllm | 2 | 6 | 0.75 (0.47-0.91) | 0.50 | 0.90 |  | 0.049 | 602,190 | 639 | 1.00 | 0 |
| S2 | opencode | qwen3.8-27b-pi-vllm | 2 | 6 | 0.75 (0.47-0.91) | 0.50 | 0.90 | 0.50 | 0.088 | 1,229,935 | 940 | 1.14 | 0 |
| S3 | opencode | qwen3.8-27b-pi-vllm | 2 | 6 | 0.75 (0.47-0.91) | 0.50 | 0.90 |  | 0.088 | 1,550,806 | 1024 | 1.00 | 6 |
| S3@oracle | opencode | qwen3.8-27b-pi-vllm | 2 | 6 | 0.75 (0.47-0.91) | 0.50 | 0.90 |  | 0.041 | 592,696 | 830 | 1.00 | 0 |
| S4 | opencode | qwen3.8-27b-pi-vllm | 2 | 5 | 0.50 (0.24-0.76) | 0.20 | 0.62 |  | 0.070 | 648,171 | 411 | 1.00 | 0 |

Token source (docs/metrics_tokens.md): proxy 35 runs
