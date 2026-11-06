# Serving open-weight models for the agent eval pipeline

How to run the shortlisted SLMs (see `docs/research/Task2_Models_Harnesses.md`) so that **k = 2–6 coding agents** in Docker can share one server at **64K+ context** with working tool calls.

Scripts are in `scripts/serve/`. The endpoint checker is `scripts/check_endpoint.py`.

**How sure each fact is.** Facts marked **[verified]** were checked on 2026-11-06, either against official docs/model cards or on our M5 Mac with Ollama 0.40.6. Facts marked **[unverified]** are recalled or inferred and still need testing. Memory figures are **estimates** worked out from each model's `config.json`; expect ±20%.

---

## 0. Quick start

```bash
# Mac dev box (Ollama). Defaults: 4 parallel slots, 64K context each, q8 KV cache, bound to 0.0.0.0
MODEL=qwen3.5:9b PARALLEL=4 CTX=65536 scripts/serve/ollama.sh

# NVIDIA box (vLLM)
MODEL=Qwen/Qwen3.6-35B-A3B-FP8 MAX_LEN=131072 MAX_SEQS=4 scripts/serve/vllm.sh

# Any box, GGUF (llama.cpp)
HF=unsloth/Qwen3.6-35B-A3B-GGUF:Q4_K_M NP=4 CTX_PER_SLOT=65536 scripts/serve/llamacpp.sh

# Ada cluster
MODEL=<org>/Qwen3.6-27B-AWQ MAX_SEQS=4 sbatch scripts/serve/slurm_vllm.sbatch

# Always, before any experiment (from the host; add --anthropic for Claude Code, --responses for Codex)
python3 scripts/check_endpoint.py --base-url http://localhost:8000/v1 --model <served-name> \
    --anthropic --responses --parallel 4 --max-tokens 512 --json-out runs/<id>/endpoint_check.json
```

From inside an agent container the server is `http://host.docker.internal:<port>`. On Linux, start the container with `--add-host=host.docker.internal:host-gateway`, and the server must listen on `0.0.0.0`. All our scripts bind `0.0.0.0` by default.

**Security.** Binding `0.0.0.0` exposes the server to your network. On a laptop on shared Wi-Fi, either pass `--api-key` (vLLM, llama.cpp) or keep `127.0.0.1`, which is enough on Docker Desktop for Mac. **[unverified]** Docker Desktop forwards `host.docker.internal` to services that listen only on the host's loopback; check this with `curl` from a container.

---

## 1. Decision table

### 1a. KV-cache cost per agent

The KV cache is the memory each conversation needs on top of the weights. This is what limits *k*. All figures are for one agent at 64K tokens, computed from `config.json` (layers × KV heads × head_dim × 2 for K and V).

| Model | Architecture | KV per 64K agent (fp16) | With q8 / fp8 KV | Weights (Q4_K_M GGUF / AWQ) | Weights (Q8 / FP8) |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | MoE, hybrid: 10 of 40 layers full attention, 2 KV heads | **1.25 GiB** | 0.6 GiB | ~22 GB (24 GB Ollama tag, includes vision) | ~38 GB |
| Qwen3.8-27B / Qwen3.6-27B | dense, hybrid: 16 of 64 layers full attention, 4 KV heads | **4 GiB** | 2 GiB | ~17 GB | ~30 GB |
| Devstral Small 2 (24B) | dense, every layer full attention, 8 KV heads | **10 GiB** | 5 GiB | ~14 GB | ~26 GB (official FP8) |
| Ornith-1.0-9B / Qwen3.5-9B | dense, hybrid: 8 of 32 layers full attention | **2 GiB** | 1 GiB | ~6 GB | ~10 GB (bf16 19 GB) |
| Qwen3-Coder-30B-A3B | MoE, every layer full attention, 4 KV heads | 6 GiB | 3 GiB | ~18 GB | ~32 GB |
| gpt-oss-20b | half the layers use a 128-token sliding window | 1.5 GiB | 0.75 GiB | ~13 GB (ships MXFP4) | n/a |
| GLM-4.7-Flash | MLA (compressed KV), 47 layers | ~3.3 GiB (only if the engine supports MLA) | — | ~18 GB | ~32 GB |

How to read this table:

- **The hybrid Qwen3.5/3.6/3.8 family is cheap per agent.** Only one layer in four keeps a KV cache. The Gated-DeltaNet layers hold a fixed state of about 30–70 MiB per sequence, whatever the context length.
- **Devstral Small 2 is expensive.** Four agents at 64K need about 40 GiB of fp16 KV. For Devstral, the KV cache, not the weights, decides what hardware we need.
- **Total memory** ≈ weights + k × KV + 1–3 GB overhead (activations, CUDA graphs, Metal buffers).
- **Tensor parallelism can double the KV cost.** With TP greater than the number of KV heads (for example Qwen3.6-35B-A3B, which has 2 KV heads, at TP=4), vLLM copies KV heads onto several GPUs.

### 1b. Hardware → engine → what fits

"Fits" means room for **k = 4 agents at 64K** unless stated otherwise.

| Hardware | Engine | Fits for k=4 @ 64K | Doesn't fit / notes |
|---|---|---|---|
| **Mac M5 24 GB** (our dev box). Ollama reports **17.8 GiB usable by the GPU** **[verified]** | Ollama (quick) or llama.cpp `llama-server` (for real parallelism, see §2.1) | Qwen3.5-9B / Ornith-9B at Q4 or Q8 with q8 KV (6–10 GB + 4 GB). gpt-oss-20b (13 GB + 3 GB, tight) | Qwen3.6-27B/3.8-27B Q4 (17 GB) leaves no room for KV. 35B-A3B Q4 (22–24 GB) doesn't fit. Devstral Q4 fits only k=1 at ~32K. You can raise the GPU memory cap with `sudo sysctl iogpu.wired_limit_mb=20480` **[unverified on M5; it resets on reboot; it can starve macOS]**. Use the Mac for pipeline development, not for the real runs. |
| **1× 11 GB** (2080 Ti cc 7.5, 1080 Ti cc 6.1) | llama.cpp (any cc). vLLM only on cc ≥ 7.5 | 9B Q4 GGUF + q8 KV: k=2 at 64K, or k=4 at 32K | Nothing ≥ 24B fits on one card |
| **4× 2080 Ti = 44 GB** (one Ada node) | vLLM, TP=4, `--dtype half`, AWQ/GPTQ (Marlin works on Turing **[verified, vLLM quant table]**) or llama.cpp with layer split | **Qwen3.6-27B/3.8-27B AWQ**: ~4 agents at 64K. **Qwen3.6-35B-A3B AWQ/GPTQ**: k=6 at 64K, ~4 at 128K (counting the KV copies at TP=4). 9B fp16 at TP=2: k=4 | Devstral AWQ: only ~2 agents at 64K. Devstral FP8 (26 GB): 1. **Risks:** (1) Gated-DeltaNet kernels on sm75 are **[unverified]**; test before relying on them, and fall back to llama.cpp GGUF if they fail. (2) fp16 can overflow on models trained in bf16 (NaNs or garbage output). (3) The cards talk over PCIe with no NVLink, so TP=4 decoding is slow. Two TP=2 replicas may give more total throughput. |
| **1× 24 GB** (3090 cc 8.6, 4090 cc 8.9) | llama.cpp / Ollama (GGUF) for 27–35B. vLLM for ≤ 20B | 9B FP8/Q8 (k=6). gpt-oss-20b (k=6). **35B-A3B at Q3_K_M/IQ4_XS (~17–19 GB) + q8 KV**: k=4 | 35B-A3B Q4_K_M leaves ~1.5 GB, so k=1. 27B Q4 + q8 KV: k=2–3. Devstral Q4: k=1 at 64K or k=2 at 32K. vLLM AWQ of 27–35B leaves only 2–4 GB of KV |
| **1× 48 GB** (A6000 cc 8.6, L40S cc 8.9) | vLLM | Qwen3.6-35B-A3B FP8 (k≈5 at 64K fp16 KV). Qwen3.6-27B/3.8-27B FP8 (k≈4, or 7 with fp8 KV). Any 4-bit model with lots of headroom | Devstral FP8: k≈2 at 64K with fp16 KV, 3 with fp8 KV. Use AWQ or 32K for k=4. A6000 has no native FP8; vLLM runs FP8 weights there as W8A16 Marlin **[verified table]** |
| **1× 80 GB** (A100 cc 8.0, H100 cc 9.0) | vLLM (or SGLang) | Everything at FP8: 35B-A3B (k≫6), 27B (k≈11 at 64K), Devstral (k≈4, 9 with fp8 KV). 27B bf16 (k≈4) | 35B-A3B bf16 (~70 GB) is too tight. **Best setup for the fan-out experiments.** |
| **2× 80 GB** | vLLM TP=2, or two replicas behind a router | bf16 for everything, k=6 at 128K | — |
| **No GPU** | OpenRouter (see Task2 §3) | — | Pin the provider and quantization |

**Rules of thumb**

- Use the **same engine, quantization, context length and max-seqs for every strategy** in one comparison.
- Below 48 GB, prefer **Qwen3.6-35B-A3B**: it has the cheapest KV and only 3B active parameters, so it decodes fast.
- Give Devstral the big GPUs.

---

## 2. Engines

### 2.0 Which API each engine exposes

| Engine | `/v1/chat/completions` + tools | Anthropic `/v1/messages` (Claude Code) | `/v1/responses` (Codex) | Source |
|---|---|---|---|---|
| **Ollama** 0.40.6 | yes | **yes**: text and `tool_use` **[verified locally]**. No `tool_choice`, no prompt caching, `budget_tokens` ignored | **yes**: text and `function_call` **[verified locally]**. Stateless only: no `previous_response_id` | docs.ollama.com `/api/openai-compatibility`, `/api/anthropic-compatibility` |
| **llama.cpp** `llama-server` | yes (needs `--jinja`, which is now on by default) | **yes** (`/v1/messages`, `/v1/messages/count_tokens`; tools need `--jinja`) | **yes** (`/v1/responses`) | tools/server/README.md **[verified docs]** |
| **vLLM** (current) | yes, with `--enable-auto-tool-choice --tool-call-parser X` | **yes** (`/v1/messages`, `/v1/messages/count_tokens`), with an official Claude Code guide | **yes** (`/v1/responses`, plus retrieve/cancel) | docs.vllm.ai online_serving, integrations/claude_code **[verified docs]** |
| **LM Studio** | yes | **yes** ("Anthropic Compatibility → Messages") | **yes** (`POST /v1/responses`; the docs say Codex is supported) | lmstudio.ai/docs/developer **[verified docs; not run here]** |
| **mlx-lm** `mlx_lm.server` | `/v1/chat/completions` only; tool support undocumented | no | no | mlx-lm SERVER.md **[verified docs]**. "Not recommended for production" |
| **SGLang** | yes (`--tool-call-parser`) | **[unverified]** | **[unverified]** | docs page checked only covers chat/completions |

Notes on the agent CLIs:

- **Claude Code** works against Ollama, llama.cpp, vLLM and LM Studio. Set `ANTHROPIC_BASE_URL=http://host.docker.internal:<port>` (no `/v1`) and `ANTHROPIC_AUTH_TOKEN=dummy`. Also set `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL=<served-name>`.
  - On vLLM the served name must not contain `/`, so `vllm.sh` sets `--served-model-name` to a lower-case basename.
  - The built-in WebSearch tool returns a 400 on local servers.
  - On vLLM ≤ 0.17.1, set `CLAUDE_CODE_ATTRIBUTION_HEADER=0`. Otherwise a per-request hash in the system prompt defeats prefix caching. (Both points are from vLLM's Claude Code page.)
- **Codex** needs `/v1/responses`. Ollama, llama.cpp, vLLM and LM Studio all have it, so Codex is not limited to Ollama/LM Studio. It can use a custom `model_providers` entry with `wire_api = "responses"` pointing at any of these **[unverified with non-gpt-oss models]**. Ollama's Responses is stateless; Codex is believed to resend the full history, so that should be fine, but this is **[unverified]**.
- **Antigravity CLI** only uses Google-hosted models, so it is out (as Task2 says).
- **OpenCode, Pi, mini-SWE-agent and OpenHands** use chat completions, which every engine supports.

### 2.1 Ollama (Mac dev box; also Linux)

Script: `scripts/serve/ollama.sh`. It starts `ollama serve` with the env vars below, pulls the model if missing, loads it with `num_ctx`, checks the loaded context in `/api/ps`, and runs the endpoint checker.

| Env var | Default | What we set | Why |
|---|---|---|---|
| `OLLAMA_NUM_PARALLEL` | **1** ([verified] in `server.log` and the FAQ) | k | With 1, parallel agents are **queued**, not batched |
| `OLLAMA_CONTEXT_LENGTH` | **4096** on our Mac (log: `vram-based default context total_vram=17.8 GiB default_num_ctx=4096`). `ollama serve --help` says "4k/32k/256k based on VRAM" | 65536–131072 | Above this, prompts are **truncated silently**. This is the #1 Ollama failure. Applies **per slot**: the FAQ says RAM scales with `NUM_PARALLEL × CONTEXT_LENGTH` |
| `OLLAMA_KV_CACHE_TYPE` | f16 | q8_0 | Halves KV memory. Applies to all models. Needs flash attention |
| `OLLAMA_FLASH_ATTENTION` | auto | 1 | |
| `OLLAMA_KEEP_ALIVE` | 5m | -1 | Stops the model unloading between slow agent turns |
| `OLLAMA_HOST` | 127.0.0.1:11434 | 0.0.0.0:11434 | So Linux Docker can reach it |
| `OLLAMA_MAX_LOADED_MODELS` | 0 (auto) | 1 | Never let a second model evict the one under test |

**Gotchas**

- **Clients can't set the context.** The OpenAI-compatible `/v1` API has no `num_ctx` field, so the server-wide `OLLAMA_CONTEXT_LENGTH`, or a Modelfile with `PARAMETER num_ctx`, is the only lever for agents. After loading, check `ollama ps` (CONTEXT column).
- **The macOS app ignores your shell's env.** Either quit the app and let the script start `ollama serve`, or run `launchctl setenv OLLAMA_NUM_PARALLEL 4` and so on, then restart the app.
- **The MLX runner appears not to batch [verified-ish, important].**
  - On Ollama 0.40.6, `qwen3.5:2b` (an `mxfp8` safetensors model that runs on the `mlx` runner) ran **serially even with `OLLAMA_NUM_PARALLEL=3`**. Three streams produced the same total tokens/s as one (~37 tok/s), and time-to-first-token rose in a staircase.
  - GGUF tags (`q4_K_M`, `q8_0`, which use the llama.cpp runner) should batch, but this is **[unverified here]**.
  - If `check_endpoint.py --parallel k` prints `looks SERIALISED`, switch to a GGUF tag or to `llama-server`.
- **Turning thinking off over `/v1`.** Only `"reasoning_effort": "none"` worked [verified]. `chat_template_kwargs` and `think:false` were ignored on `/v1/chat/completions`. On the native `/api/chat`, use `"think": false`.
- **Reasoning field names differ.** Ollama returns reasoning in `message.reasoning`. vLLM now uses `reasoning` (it replaced `reasoning_content`). Some clients still read the old name.
- **Pulling from Hugging Face:** `ollama pull hf.co/<repo>-GGUF:Q4_K_M` (for example Ornith: `hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF`; its card says "to be published", so check it exists).

### 2.2 llama.cpp `llama-server` (Mac, CUDA of any generation, CPU)

Script: `scripts/serve/llamacpp.sh`. It is the most portable engine: it is the only one for the 1080 Ti nodes and the most predictable way to get real parallel slots on the Mac.

```bash
llama-server -hf unsloth/Qwen3.6-35B-A3B-GGUF:Q4_K_M --alias qwen3.6-35b-a3b \
  --host 0.0.0.0 --port 8080 --jinja -np 4 -c 262144 --no-kv-unified \
  -ngl all -fa on -ctk q8_0 -ctv q8_0 --metrics
```

Flags **[verified, README]**:

- `--jinja`: uses the model's own chat template, which tool calls require. It is the default now, but pass it anyway.
- `-np N`: number of parallel slots. The default -1 means auto.
- `-c`: total context. The default 0 takes it from the model, which can be 256K and use a lot of memory.
  - With `--no-kv-unified`, each slot gets `c / np`, so the script passes `-c = NP × CTX_PER_SLOT`. This is long-standing behaviour; check `n_ctx` in `GET /slots`.
  - Alternatively, `--kv-unified-per-slot N` caps each slot inside one shared pool.
- `--host`: the default is 127.0.0.1.
- `--port`: the **current default is 9931**, not the old 8080, so always pass it.
- `-ngl`: also accepts `all`.
- `-ctk/-ctv`: KV cache type (f16, q8_0, q4_0, …).
- `-fa on`: flash attention.
- `--reasoning-budget N`: limits thinking tokens. `0` means think immediately ends.
- `--chat-template-kwargs '{"enable_thinking":false}'`: turns thinking off.
- `-ts 1,1`: splits layers across GPUs.
- `--fit`: on by default. It shrinks unset options until the model fits. Pin `-c` and `-np` explicitly so `--fit` can't silently cut them.

Devstral Small 2 GGUFs need a recent llama.cpp; its model card points to PR #17945.

### 2.3 Mac alternatives: LM Studio and mlx-lm

**LM Studio** has a GUI and the `lms` CLI; its server includes MLX and llama.cpp engines.

```bash
lms server start --port 1234 --bind 0.0.0.0     # [verified docs] (or LMS_SERVER_HOST)
lms load <model> --context-length 65536 --gpu max --identifier qwen-test --ttl 0
```

- It exposes chat completions, `/v1/responses` and Anthropic `/v1/messages`, so it covers Claude Code and Codex.
- `lms load` documents no `--parallel` flag. Parallel requests have to be configured in the GUI's model load settings **[unverified]**. Run `check_endpoint.py --parallel k` to see whether requests actually batch.
- `lms load --estimate-only` prints a memory estimate before loading.

**mlx-lm** (`mlx_lm.server --model mlx-community/<model>-4bit`) is fast on Apple Silicon, but it only has `/v1/chat/completions`. Its docs say "not recommended for production", and `--kv-bits` **disables batching**. Use it for quick speed comparisons, not for agent runs.

### 2.4 vLLM (NVIDIA; the main engine for the real runs)

Script: `scripts/serve/vllm.sh`. It picks the parsers from the model name, forces `--dtype half` on cc < 8.0, and prints the exact command.

```bash
vllm serve Qwen/Qwen3.6-35B-A3B-FP8 --served-model-name qwen3.6-35b-a3b-fp8 \
  --host 0.0.0.0 --port 8000 --max-model-len 131072 --max-num-seqs 4 \
  --gpu-memory-utilization 0.90 --tensor-parallel-size 1 \
  --enable-prefix-caching --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder --reasoning-parser qwen3
```

| Flag | Guidance |
|---|---|
| `--max-model-len` | The longest context per request. Use ≥ 65536 for agents and 131072 if memory allows. vLLM refuses to start if even **one** sequence of this length doesn't fit in the KV pool. |
| `--max-num-seqs` | Upper limit on sequences batched at once. Set it to k, or a little above for subagents. Concurrency is also limited by KV pool size; at startup the log prints "Maximum concurrency for N tokens per request: X×", so check that X ≥ k. |
| `--gpu-memory-utilization` | 0.90 by default here. Lower it if CUDA graphs run out of memory; raise it to 0.95 on a dedicated card. |
| `--tensor-parallel-size` | Number of GPUs. KV heads are copied when TP > number of KV heads. |
| `--kv-cache-dtype fp8` | Halves the KV cache. Natively supported on Ada/Hopper; **[unverified]** quality and speed on Ampere and Turing. |
| `--default-chat-template-kwargs '{"enable_thinking": false}'` | Sets thinking off for the whole server **[verified docs]**. A request can still override it. |
| `--generation-config auto` | Uses the sampling defaults from the model's `generation_config.json`. Record which values were actually used. |

**Tool and reasoning parsers.** These are picked automatically in `vllm.sh`. Override them with `TOOL_PARSER=` / `REASONING_PARSER=`.

| Model | `--tool-call-parser` | `--reasoning-parser` | Source |
|---|---|---|---|
| Qwen3.6-35B-A3B, Qwen3.6-27B, Qwen3.8-27B, Qwen3.5-* | `qwen3_coder` | `qwen3` | Qwen3.6 card and vLLM recipe **[verified]**. The Qwen3.8 card lists no parser; we assume it is the same as 3.6 **[unverified]** |
| Ornith-1.0-9B | `qwen3_xml` (+ `--trust-remote-code`) | `qwen3` | Ornith card **[verified]**. Needs vLLM ≥ 0.19.1 |
| Qwen3-Coder-30B-A3B | `qwen3_coder` (vLLM's docs table also lists `qwen3_xml` for it) | none | vLLM tool-calling docs |
| Devstral Small 2 | `mistral` | none | Devstral card **[verified]**. Needs `mistral_common ≥ 1.8.6` |
| gpt-oss-20b | `openai` | none needed (harmony format) **[unverified]** | vLLM tool-calling docs, Claude Code page |
| GLM-4.7-Flash | `glm47` | `glm45` **[unverified for 4.7]** | vLLM tool-calling docs |

The two Qwen-style parsers read the same `<tool_call><function=…><parameter=…>` XML format. `qwen3_xml` is the newer, stream-safe one. If tool calls fail when streaming, try the other.

**Quantization on cc 7.5 (2080 Ti)**, from vLLM's hardware table **[verified]**:

- Works: AWQ, GPTQ, Marlin (GPTQ/AWQ/FP8 weight-only), bitsandbytes, GGUF and INT8 W8A8.
- Doesn't work: FP8 W8A8 compute, W4A8, and Marlin MXFP4. So gpt-oss's MXFP4 has no Turing Marlin path.
- Also use `--dtype half`, since there is no bf16.
- Pick **AWQ or GPTQ 4-bit** checkpoints. An FP8 checkpoint loads as W8A16, but 8-bit weights double the memory.
- Some newer kernels need cc ≥ 8.0, and FlashAttention-2 needs Ampere. If startup fails, try `--enforce-eager` (no CUDA graphs) or another attention backend **[unverified]**.

**Hybrid Qwen models (Gated DeltaNet).**

- Need vLLM ≥ 0.17 (recipe) or ≥ 0.19 (Qwen3.6 card).
- Prefix caching for these layers is "experimental in align mode" (recipe). Agents depend on prefix caching for speed, so measure the time to first token on turn 2 and later.
- If you hit CUDA-graph or Mamba-cache memory errors, lower `--max-cudagraph-capture-size` (default 512).

### 2.5 SGLang (optional)

```bash
python -m sglang.launch_server --model-path Qwen/Qwen3.6-35B-A3B --host 0.0.0.0 --port 8000 \
  --tp-size 1 --context-length 131072 --mem-fraction-static 0.85 --max-running-requests 4 \
  --reasoning-parser qwen3 --tool-call-parser qwen3_coder
```

These flags come from the Qwen3.6 card **[verified]**; `--max-running-requests` is from memory **[unverified]**.

SGLang often has faster prefix caching (RadixAttention) for agent workloads. However, Anthropic and Responses support is **[unverified]**, and so is Turing support. Use it only on Ampere or newer, with the same validation steps as vLLM.

---

## 3. SLURM (IIIT Ada)

Script: `scripts/serve/slurm_vllm.sbatch`. It requests 4 GPUs, sets `TP` to the GPU count and `--dtype half`, and puts `HF_HOME` on `/scratch/$USER`. It starts `vllm.sh`, waits for `/health`, runs `check_endpoint.py` (results go to `logs/vllm-<job>-check.json`), and prints the tunnel command.

```bash
mkdir -p logs
MODEL=<org>/Qwen3.6-27B-AWQ MAX_LEN=65536 MAX_SEQS=4 VENV=$HOME/venvs/vllm \
  sbatch scripts/serve/slurm_vllm.sbatch
squeue --me; tail -f logs/vllm-<jobid>.out
```

**Reaching the server from your laptop**

```bash
ssh -N -L 8000:<gnodeXX>:8000 <user>@ada.iiit.ac.in            # Mac: containers use host.docker.internal:8000
ssh -N -L 0.0.0.0:8000:<gnodeXX>:8000 <user>@ada.iiit.ac.in    # Linux + Docker host-gateway
```

You can also run the agent containers on the Ada login node or a CPU node and point them straight at `http://<gnodeXX>:8000`, if node-to-node traffic is open.

**Ada specifics to check (all [unverified]):**

- account and partition names (`sacctmgr show assoc user=$USER`)
- the maximum walltime
- whether compute nodes have internet; if not, run `huggingface-cli download` on the login node into `$HF_HOME`
- that `/scratch` is node-local, so weights must be re-copied whenever the job lands on a different node
- which CUDA module matches the vLLM wheel

Also check that the GPUs really are 2080 Ti (cc 7.5) with `nvidia-smi --query-gpu=name,compute_cap --format=csv`. Some Ada nodes have 1080 Ti (cc 6.1); vLLM won't run there, so use `llamacpp.sh`.

---

## 4. What to record for reproducibility

Record all of this in each run's metadata. `check_endpoint.py --json-out` captures the endpoint part, and the serve scripts print the exact command line.

| Field | Example / how to get it |
|---|---|
| Engine and version | `vllm --version`, `ollama --version`, `llama-server --version`, LM Studio app version, and the Docker image digest if containerised |
| Exact launch command and env | the line printed by our scripts, plus every `OLLAMA_*` value |
| Model repo and **revision** | HF commit hash (`huggingface-cli scan-cache`) or Ollama digest (`ollama list` ID) |
| Quantization | e.g. AWQ-4bit, `Q4_K_M` GGUF, FP8, plus KV cache dtype |
| Hardware | GPU model × count, VRAM, driver/CUDA (`nvidia-smi`), or Mac chip + RAM |
| Context | `--max-model-len` / `CTX_PER_SLOT` / Ollama loaded `context_length` (from `ollama ps`, not what you asked for) |
| Concurrency | `--max-num-seqs` / `-np` / `OLLAMA_NUM_PARALLEL`, and the k agents actually used |
| Parsers | tool-call parser, reasoning parser, chat template (default or overridden) |
| Sampling | temperature, top_p, top_k, min_p, presence/repetition penalty, seed, max_tokens. Note which ones the harness sends and which are server defaults |
| Thinking | on or off, and the reasoning effort (Qwen3.8 defaults to `xhigh`) |
| Throughput baseline | the `check_endpoint.py --parallel k` row: aggregate tok/s, p50/max latency, TTFT |

Recommended sampling settings from the model cards **[verified]**:

- Qwen3.6, thinking, coding: temperature 0.6, top_p 0.95, top_k 20, presence_penalty 0.
- Qwen3.8, thinking: temperature 1.0, top_p 0.95, top_k 20.
- Ornith: temperature 0.6, top_p 0.95, top_k 20.
- Devstral: temperature 0.15.

---

## 5. Common failure modes

1. **Tool calls fail without an error.**
   - The model writes `<tool_call>…` or `[TOOL_CALLS]…` as plain text in `content`, and `tool_calls` is empty.
   - Cause: the parser is wrong or missing (vLLM), `--jinja` is off or the GGUF has a broken template (llama.cpp), or the Ollama model tag has no `tools` capability (`ollama show <m>`).
   - The harness then sees a chatty model that never acts.
   - `check_endpoint.py` detects raw markup and reports `wrong/missing --tool-call-parser`.
2. **Context gets truncated without warning.**
   - Ollama's default is 4096 on a 24 GB Mac. Agents' 30K-token prompts get cut from the front, so the model "forgets" the task or the tool list.
   - Fix: `OLLAMA_CONTEXT_LENGTH`, then check `ollama ps`.
   - On llama.cpp the same happens when `-c` is divided across `-np` slots.
   - vLLM rejects over-long prompts with a 400 instead, which is better, but the harness has to surface it.
3. **Thinking tokens use up the budget.**
   - Qwen3.5+, Ornith and GLM think by default. With small `max_tokens`, the answer comes back with empty `content` and `finish_reason=length` (seen locally with qwen3.5:2b at 64 tokens).
   - Agents' turns then show up empty, or reasoning leaks into `content` if no reasoning parser is set.
   - Long thinking also multiplies latency and KV use.
   - Decide thinking on or off per experiment, and record it.
4. **Parallel agents get serialised.** Causes: `OLLAMA_NUM_PARALLEL=1` (the default), the Ollama MLX runner, `-np 1`, or `--max-num-seqs` / KV pool smaller than k. Fan-out timings then measure queueing, not the strategy. `check_endpoint.py --parallel k` warns about this.
5. **KV-cache thrashing in vLLM.** When the KV pool is too small for k long contexts, vLLM pre-empts and recomputes sequences. Look for `Preempted` or `preemption` in the log and a rising `vllm:num_preemptions_total` in `/metrics`. Reduce k or the context, quantize the KV cache, or use a bigger GPU.
6. **fp16 on Turing.** Models trained in bf16 can produce NaNs or repeated garbage in fp16. Sanity-check the output, not just the status codes.
7. **Model name mismatches.** Claude Code rejects names containing `/`. Ollama names include tags (`qwen3.5:9b`). The `models` row in `check_endpoint.py` shows what the server calls the model.
8. **Linux Docker can't reach the server.** Two causes: a missing `--add-host=host.docker.internal:host-gateway`, or the server or SSH tunnel bound to 127.0.0.1.
9. **The macOS app keeps old settings.** Env vars exported in a shell don't reach the Ollama menu-bar app. `ollama.sh` warns when it finds a server already running.
10. **Ollama's limits.** It ignores `tool_choice` on `/v1/chat/completions` and Anthropic `/v1/messages`. Harnesses that force `tool_choice: required` won't get it.

---

## 6. `check_endpoint.py` reference

```text
python3 scripts/check_endpoint.py --base-url URL/v1 --model NAME
    [--anthropic] [--anthropic-base-url URL] [--responses] [--parallel N]
    [--max-tokens 256] [--temperature 0] [--timeout 120] [--no-think]
    [--engine auto|ollama|other] [--extra-body JSON] [--api-key KEY] [--json-out FILE]
```

It runs these checks:

- `models`: the model is listed (only a WARN if not).
- `chat`: a short completion returns non-empty content.
- `tool_call`: a `read_file` tool call has a correct name, JSON arguments containing `path`, and an id.
- `tool_roundtrip`: after the tool result is sent back, the model's answer contains the secret word from the fake file.
- `anthropic_text` / `anthropic_tool`: the same checks on `/v1/messages` (`tool_use` block).
- `responses_text` / `responses_tool`: the same checks on `/v1/responses` (`function_call` item).
- `parallel xN`: N concurrent streamed requests. It reports total and per-request tok/s, p50/max latency and the maximum time to first token, and flags serialised serving.

Other behaviour:

- `--no-think` sends `reasoning_effort:"none"` to Ollama (detected via `/api/version`) and `chat_template_kwargs.enable_thinking=false` to everything else.
- The exit code is 1 if any check FAILs.

**Results on the dev box** (M5 24 GB, Ollama 0.40.6, `qwen3.5:2b`; `qwen3.5:9b` was still downloading):

```text
--max-tokens 64 --no-think --anthropic --responses --parallel 4
models PASS | chat PASS | tool_call PASS read_file({"path": "README.md"}) | tool_roundtrip PASS 'PINEAPPLE'
anthropic_text PASS | anthropic_tool PASS | responses_text PASS | responses_tool PASS
parallel x4 PASS*  agg 36 tok/s, per-req 9-35 tok/s   (*before the serialisation heuristic was added;
                                                       re-runs flag it: requests were queued, NUM_PARALLEL=1)
With thinking on (default) and --max-tokens 64: chat FAIL "only reasoning, no content", tool_roundtrip FAIL
(the tool call itself still PASSed) -> give thinking models >= 512-1024 tokens or turn thinking off.
With OLLAMA_NUM_PARALLEL=3 on a second server (port 11435): still serialised on the mlx runner (see 2.1).
```
