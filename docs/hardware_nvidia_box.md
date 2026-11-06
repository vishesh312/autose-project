# NVIDIA box: hardware and models used

Hardware (no hostnames or identifiers on purpose):

| | |
|---|---|
| GPUs | 3 x NVIDIA RTX 5000 Ada Generation, 32 GB each (shared with other users; our runs use one GPU only) |
| Driver / CUDA | 560.35.05 / CUDA 12.6 |
| CPU | Intel Xeon Gold 5317 @ 3.0 GHz, 48 logical CPUs |
| RAM | 251 GB |
| OS | Ubuntu 24.04 LTS |
| Docker | not available to us; runs use the no-Docker host-pool mode |

Models served (vLLM, a single GPU each time):

| Model | Precision | vLLM | Context | Notes |
|---|---|---|---|---|
| Qwen2.5-7B-Instruct | bf16 | 0.8.5 | 32768 | hermes tool parser; used for the core subset runs (S0/S1/S2) |
| Qwen3.8-27B (RedHatAI INT4 build) | 4-bit | 0.33.0 | 65536 | thinking off, fp8 KV cache; one-bundle trial (click task2800); status: not yet run |

Harness: OpenCode 1.19.5, run directly on the host.
