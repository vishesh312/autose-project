# Task 2: Models & Harnesses (SLM focus)
**What we mean by SLM:** an open-weight model with at most ~35B parameters in total, small enough to run ourselves on one GPU or a few small ones.

**Terms used below:**
- **Harness:** the agent program around the model. It gives the model tools, a prompt and a loop.
- **MoE, "3B active":** a mixture-of-experts model. Only a small part of it (here 3B parameters) runs for each token, so it is fast for its size.
- **Vendor score:** a score the model's makers published themselves. **Independent score:** one measured by someone else.
- **4-bit / 8-bit / bf16:** how compressed the weights are. Fewer bits means less memory and slightly lower quality.
- **KV cache:** extra GPU memory each running conversation needs, on top of the weights.

## TL;DR

- **Models.**
  - Main three:
    - **Qwen3.8-27B:** best vendor scores, but no independent results yet.
    - **Qwen3.6-35B-A3B:** fastest, with recent independent results.
    - **Devstral Small 2:** a second model family, and the best independent score on the list.
  - **Ornith-1.0-9B** as the tiny tier.
  - **Qwen3-Coder-30B-A3B** only to repeat CooperBench's results.
  - One frontier API model on a small subset, to show the upper limit.
- **Harnesses.**
  - **Pi** and **OpenCode** are the core. Both work with any OpenAI-compatible server and record token use.
  - **mini-SWE-agent** is the control.
  - Optional: oh-my-pi (Pi plus parallel subagents), and Claude Code pointed at a local Anthropic-compatible server.
  - Codex only runs gpt-oss locally. Antigravity's CLI only runs its own hosted models, so it can't run our SLMs.
- **Compute.**
  - Every model on the list fits on one 24 GB GPU at 4-bit. Qwen3.6-35B-A3B only just fits.
  - IIIT-H's Ada cluster has 2080 Ti nodes (4 GPUs × 11 GB each), which are enough for a pilot.
  - Every shortlisted model except Devstral Small 2 and Ornith is also on OpenRouter, where a task costs a few cents.
- **Caveat.** Most SLM scores come from the vendors themselves, each run on a different harness. Independent SWE-rebench scores exist for 6 of our models, but they were measured on different months of tasks, so they can't be compared directly either. That is why our own baseline (each task run on its own) is the comparison that counts.

## 1. SLM shortlist

| Model | Size | Licence | Context | Vendor scores | 4-bit weights | OpenRouter $ in / out per 1M tokens |
|---|---|---|---|---|---|---|
| **Qwen3.8-27B** (Aug 2026) | 27B dense, hybrid attention | Apache-2.0 | 262K | SWE-bench Pro 61.7 (in Claude Code, on Qwen's own corrected copy of Pro). Terminal-Bench 2.1 73.0 | ~16 GB | 0.15 / 1.88 |
| **Qwen3.6-35B-A3B** (Apr 2026) | 35B MoE, 3B active | Apache-2.0 | 262K | Verified 73.4, Terminal-Bench 2.0 51.5 | ~22 GB | 0.10 / 0.90 |
| Qwen3.6-27B (Apr 2026) | 27B dense | Apache-2.0 | 262K | Verified 77.2 | ~16 GB | 0.45 / 2.70 |
| **Devstral Small 2** (Dec 2025) | 24B dense | Apache-2.0 | 256K | Verified 68.0, Terminal-Bench 2 22.5 | ~14 GB (official FP8 ≈ 26 GB) | not on OpenRouter (Mistral API only) |
| GLM-4.7-Flash (Jan 2026) | ~31B MoE, ~3B active | MIT | 200K | Verified 59.2 | ~18 GB | 0.06 / 0.40 |
| Muse Glimmer 30B (Aug 2026) | 30B dense | Apache-2.0 | 131K | Verified 76.0, Terminal-Bench 2.1 51.7 | ~17 GB | 0.30 / 1.20 |
| **Ornith-1.0-9B** (2026) | 9B dense | MIT | 256K | Verified 69.4 and Pro 42.9 (both in OpenHands). Terminal-Bench 2.1 43.1 | ~6 GB (bf16 ≈ 19 GB) | not on OpenRouter (self-host only) |
| gpt-oss-20b (Aug 2025) | 21B MoE, 3.6B active | Apache-2.0 | 131K | OpenAI: Verified 60.7 at high reasoning effort. NVIDIA and Z.ai both measured only 34.0 | ~13–16 GB (ships in 4-bit MXFP4) | 0.02 / 0.09 |
| Qwen3-Coder-30B-A3B (Jul 2025) | 30B MoE, 3B active | Apache-2.0 | 262K | No vendor score used. CooperBench result in the Notes below | ~17 GB | 0.15 / 0.60 |

**Independent results (SWE-rebench).** SWE-rebench runs every model on the same agent setup, using new GitHub tasks collected each month. Each model is scored only on tasks from its own date range.

| Model | Tasks solved | Tasks from | Cost per task |
|---|---|---|---|
| Devstral Small 2 | **36.4%** | Nov 2025 – Feb 2026 | $0.09 |
| Qwen3.6-27B | **31.2%** | mid-May – Jun 2026 | $0.62 |
| GLM-4.7-Flash | 30.1% | Jan – Feb 2026 | $0.07 |
| Gemma 4 31B (not shortlisted) | 25.1% | Feb – mid-May 2026 | $0.32 |
| Qwen3.6-35B-A3B | **24.7%** | mid-May – Jun 2026 | $0.27 |
| Qwen3-Coder-30B-A3B | 21.6% | Jul 2025 – Jan 2026 | not reported |
| gpt-oss-20b | 8.1% | Aug 2025 | not reported |

- Only the two Qwen3.6 models have scores on the newest tasks (mid-May to June 2026). The leaderboard hasn't been updated since early July 2026.
- Scores move a lot with the task months chosen. For example, Qwen3.6-35B-A3B ranges from 20.0% to 36.7% depending on the month.
- Devstral Small 2, GLM-4.7-Flash and Gemma 4's task ranges start before the model was released, so some tasks may have been in their training data. Counting only tasks from after its release, Gemma 4 drops to 16.4%.
- Qwen3.8-27B, Muse Glimmer, Ornith and Nemotron 3 Nano are not on SWE-rebench at all.

**Notes on the scores.**
- "Verified" means SWE-bench Verified.
- Vendors use different harnesses and benchmark versions (e.g. Terminal-Bench 2.0 vs 2.1). Don't compare vendor scores with each other or with SWE-rebench.
- **CooperBench (Qwen3-Coder-30B-A3B):** two agents worked on separate features of the same repo, and their changes then had to be merged successfully. Qwen3-Coder managed this in 14.7% of tasks, against 27.9% for GPT-5. That was with the agents not talking to each other; with talking allowed, it was 13.3% vs 27.9%.
- "4-bit weights" is the size of the weights alone (typical Q4_K_M GGUF files). The KV cache needs memory on top.

**Also looked at, but not shortlisted:**
- Weaker results or less evidence:
  - Nemotron 3 Nano 30B-A3B: NVIDIA reports 38.8 on SWE-bench with OpenHands.
  - Gemma 4 31B: 66.6 Verified in Meta's comparison table (Google publishes no SWE-bench score), 25.1% on SWE-rebench.
  - Qwen3.5-9B, Ministral 3 (3B/8B/14B), Granite 4.2 8B, LFM 2.5 24B-A2B and Cohere North-Mini-Code.
- Called "small" but too big for us: Inkling-Small (276B total / 12B active), Qwen3-Coder-Next (80B / 3B), DeepSeek-V4-Flash (284B).

**Picks.**
- **Main three:** Qwen3.8-27B, Qwen3.6-35B-A3B and Devstral Small 2.
  - They mix dense and MoE models, two model families and both tool-call formats (Qwen's XML style and Mistral's JSON style).
  - Qwen3.8-27B has the best vendor scores but nothing independent yet.
  - The two others have independent scores.
- **Tiny tier:** Ornith-1.0-9B. Nobody has checked its scores independently yet. gpt-oss-20b is the fallback.

## 2. Harnesses for SLMs

| Harness | Can it run a local SLM? | How | Verdict |
|---|---|---|---|
| **Pi** | Yes | Add a custom provider in `models.json` (`baseUrl`, `api: "openai-completions"`) | **Core.** Only 4 tools are on by default (read, bash, edit, write) and the prompt is short, which suits small models. `--mode json` records tokens and cost |
| **OpenCode** | Yes | `@ai-sdk/openai-compatible` provider with `options.baseURL`. The docs name Ollama, LM Studio and llama.cpp. They don't mention vLLM, but it should work the same way | **Core.** Has subagents, for the run where the harness splits the work itself. `opencode export` saves each session; `opencode stats` gives total tokens and cost |
| **mini-SWE-agent** | Yes | LiteLLM, so any OpenAI-compatible server | **Control.** Its only tool is bash, and it is the harness behind public leaderboards. v2 uses native tool calls by default, so the server's tool-call parser must work (or switch to its text-based mode) |
| oh-my-pi | Yes | `~/.omp/agent/models.yml`. The docs name Ollama, LM Studio, llama.cpp and vLLM | Optional. Pi plus subagents that run in parallel. Giving each subagent its own copy of the files is an opt-in setting |
| Claude Code | Unofficially | Set `ANTHROPIC_BASE_URL` to an Anthropic-compatible server: Ollama ≥ 0.14, LM Studio ≥ 0.4.1, or a proxy in front of vLLM | Optional. Vendors already test SLMs in it: Qwen3.8-27B's SWE-bench Pro score, and one Ornith Terminal-Bench run (40.6) |
| OpenHands | Yes | LiteLLM | Optional. CooperBench used it, so it lets us repeat their numbers |
| Codex CLI | Barely | `codex --oss --local-provider ollama` (or `lmstudio`). Uses gpt-oss-20b by default. Only works with servers that support the Responses API, because Codex removed chat-completions support | Low. In practice gpt-oss only |
| Antigravity | No, from the CLI | The CLI only offers Google-hosted models (Gemini, Claude and GPT-OSS-120B). The separate Antigravity SDK can use local models, but the CLI can't | Drop |

## 3. Where to run them

| Hardware | What fits | Notes |
|---|---|---|
| IIIT-H Ada node: 4 × RTX 2080 Ti or GTX 1080 Ti (11 GB each) | Ornith-9B at 4-bit on one GPU. Any 24–35B model at 4-bit split across 2–4 GPUs | See the Ada limits below. Good enough for the pilot |
| 1 × 24 GB (RTX 3090 / 4090) | Any model on the list at 4-bit (35B-A3B only just fits, leaving ~2 GB for the KV cache); Ornith-9B in bf16 | The KV cache limits how many agents one server can run at once |
| 1 × 48–80 GB (A6000, L40S, A100, H100) | 27–35B models at 8-bit or bf16, with room for *k* agents at once | Best setup for the fan-out experiments |
| No suitable GPU | OpenRouter, with the provider fixed and `require_parameters: true` | Pilot (~130 task-runs): about $35 for Qwen3.6-35B-A3B, at SWE-rebench's measured $0.27 per task |

**Ada limits.**
- vLLM needs a GPU with CUDA compute capability 7.5 or higher. The 2080 Ti (7.5) qualifies; the 1080 Ti (6.1) doesn't. Use llama.cpp (GGUF files) on the 1080 Ti nodes.
- The 2080 Ti has no native bf16 or FP8 support. Use fp16, or AWQ/GPTQ 4-bit weights.
- Devstral's official weights are FP8 (~26 GB). vLLM's docs say it can still load FP8 weights on a 2080 Ti, but they would need 3–4 of the 11 GB cards. A 4-bit community version is easier.
- Check that newer model designs (hybrid attention) actually run on these older GPUs.
- Long contexts will be slow.

## 4. What to get right with SLMs

1. **The server is part of the experiment.**
   - Parallel agents share one inference server, so fan-out can only be as fast as that server.
   - Record the engine, GPU, quantization, `--max-num-seqs` and context length.
   - Use the same server setup for every strategy.
2. **Tool-call parsers.** With the wrong parser, tool calls fail without any error. Always pass `--enable-auto-tool-choice`, plus:
   - Qwen3.6: `--tool-call-parser qwen3_coder --reasoning-parser qwen3`
   - Ornith: `--tool-call-parser qwen3_xml --reasoning-parser qwen3`
   - Devstral: `--tool-call-parser mistral`

   Test 5 tasks for every model × harness pair before the real runs.
3. **Context length.**
   - Agent runs easily go past 32K tokens, so serve with at least 128K (`--max-model-len`).
   - Leave enough KV-cache memory for *k* agents running at once.
4. **Fix the sampling settings and reasoning effort.** Unlike closed APIs, we can fix temperature and seed, which makes runs easier to repeat.
   - Use each model card's recommended settings. Ornith: temperature 0.6, top_p 0.95. Devstral: temperature 0.15.
   - Qwen3.8-27B thinks at `xhigh` reasoning effort by default. Set the level explicitly.
5. **One quantization per model.**
   - Use 8-bit where memory allows, and report what we used.
   - On OpenRouter, providers serve the same model at different quantizations, and some don't support tool calls at all.
6. **Expect low scores.**
   - In CooperBench, two Qwen3-Coder-30B-A3B agents succeeded about half as often as two GPT-5 agents.
   - With more agents (larger *k*), SLM scores may drop close to zero.
   - Run one frontier API model on a subset to show the gap.

## 5. Proposed pilot

| | Choice |
|---|---|
| Harnesses | Pi, OpenCode (+ mini-SWE-agent as the control) |
| Models | Qwen3.6-35B-A3B, Qwen3.8-27B (+ Devstral Small 2 if time) |
| Strategies | Isolated (each task on its own), sequential, naive fan-out + LLM resolver |
| Data | 5–10 CooperBench tasks, *k* = 2–3 |
| Anchor | Qwen3-Coder-30B-A3B in OpenHands on a few CooperBench tasks, to repeat their numbers |
| Serving | vLLM on one GPU machine (an Ada 2080 Ti node or better), with the same setup throughout |

**Open question for the team:** do we have anything bigger than Ada, such as a lab server or cloud credits? On Ada alone, fan-out timings may mostly measure a slow server, not the strategy.

## Sources

- **Model cards:** [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) · [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) · [Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) · [Devstral Small 2](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512) · [Ornith-1.0-9B](https://huggingface.co/ornith-ai/Ornith-1.0-9B) · [GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash) · [Muse Glimmer 30B](https://huggingface.co/meta-models/Muse-Glimmer-30B) · [gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) and [paper](https://arxiv.org/abs/2508.10925) · [Qwen3-Coder-30B-A3B](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct) · [Nemotron 3 Nano](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)
- **4-bit sizes:** [Qwen3.6-35B-A3B GGUF (unsloth)](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF) and the GGUF repos linked from each model card
- **Secondary coverage:** [Inkling-Small size](https://www.unite.ai/thinking-machines-lab-unveils-inkling-its-first-open-weights-multimodal-ai-model/) · [Small code LLMs for agents (Modal)](https://modal.com/resources/best-small-open-source-code-llms-ai-agents)
- **Independent results:** [SWE-rebench](https://swe-rebench.com/) · [CooperBench (arXiv 2601.13295)](https://arxiv.org/html/2601.13295)
- **Prices:** [OpenRouter models API](https://openrouter.ai/api/v1/models) (pulled 4 Nov 2026) · [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- **Harnesses:** [Pi](https://github.com/earendil-works/pi) ([models doc](https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/models.md)) · [OpenCode providers](https://opencode.ai/docs/providers/) · [oh-my-pi](https://github.com/can1357/oh-my-pi) · [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) · [Claude Code with Ollama](https://ollama.com/blog/claude) · [Claude Code with LM Studio](https://lmstudio.ai/blog/claudecode) · [Codex `--oss` guide](https://codex.danielvaughan.com/2026/05/03/codex-cli-gpt-oss-local-models-ollama-lm-studio-mlx-setup-guide/) · [Antigravity models](https://antigravity.google/docs/models) · [Antigravity headless](https://antigravity.google/docs/cli/headless)
- **Compute:** [IIIT-H infrastructure (Ada)](https://www.iiit.ac.in/infrastructure/) · [vLLM GPU requirements](https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html) · [vLLM quantization support by GPU](https://docs.vllm.ai/en/latest/features/quantization/index.html)
