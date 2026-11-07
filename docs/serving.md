# Serving on an RTX 4090 with vLLM

All data in this project is synthetic; the plant is fictional. This page describes how the agent
was served on a local RTX 4090 with vLLM, what the serving profile showed, and what went wrong on
the way. Agent results are in the [README](../README.md#agent-evaluation) and
[CHANGELOG](../CHANGELOG.md).

## Setup

- **Hardware.** One RTX 4090 (24 GB) in a Windows PC, running vLLM inside WSL2 (Ubuntu 24.04)
  with mirrored networking. The agent reaches it over a private network.
- **Engine.** vLLM 0.30.0.
- **Model.** Nemotron 3.5 Lightning 30B-A3B (hybrid mixture-of-experts, about 3B active) in
  NVFP4, served under the name `lightning`. The 4090 has no native FP4, so vLLM runs the NVFP4
  weights through Marlin weight-only FP4 kernels.
- **KV cache.** vLLM reported 593,920 tokens of KV cache.
- **Other models, same GPU, one at a time:** Qwen3-8B (FP8) and Qwen3.6-27B (AWQ INT4) for the
  agent, and two embedding models for retrieval (see [Other models](#other-models)).

The serve flags, and why:

| Flag | Value | Why |
|---|---|---|
| `--max-model-len` | 32768 | Fits the agent's prompts with room for thinking; leaves memory for the KV cache. |
| `--max-num-seqs` | 8 | Up to 8 requests batched at once, matching the serving profile's largest level. |
| `--kv-cache-dtype` | fp8 | Halves KV cache memory compared with 16-bit. |
| `--enable-prefix-caching` | on | Reuses the cache for repeated prompt prefixes (see Results). |
| `--reasoning-parser` | `nemotron_v3` | Separates the thinking from the answer. Per the model card. |
| `--tool-call-parser` | `qwen3_coder` | Turns the model's tool-call format into OpenAI tool calls. Per the model card. |

A generic command (placeholders, no real paths or hosts):

```bash
vllm serve <model-dir> \
  --served-model-name lightning \
  --port <port> \
  --max-model-len 32768 \
  --max-num-seqs 8 \
  --kv-cache-dtype fp8 \
  --enable-prefix-caching \
  --reasoning-parser nemotron_v3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
# Set an API key through the environment (for example VLLM_API_KEY), not on the command line.
```

**How the eval reaches it.** `.env` sets `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL` (the
server's `/v1` address) and `LLM_API_KEY_FILE` (a file outside the repository holding the key).
None of these values is in the repository. The configurations are `vllm-4090-nemotron-lightning`
(thinking off) and `vllm-4090-nemotron-lightning-think` (thinking on, `LLM_MAX_TOKENS` 4096) in
[eval/configs.yaml](../eval/configs.yaml); both set `LLM_MODEL: lightning` and pass
`enable_thinking` through `chat_template_kwargs`.

## Results

Serving profile: one fixed prompt, streamed, 256 tokens, thinking off, 3 rounds per user, all
users starting together. Raw numbers are in
[eval/profile/](../eval/profile/vllm-4090-nemotron-lightning-prefix-on.md). No request failed.

| Users | Prefix caching | Time to first token, median | Decode per request, median | Throughput, all users |
|---|---|---|---|---|
| 1 | on | 0.50 s | 151.5 tok/s | 105.5 tok/s |
| 2 | on | 0.54 s | 131.9 tok/s | 182.0 tok/s |
| 4 | on | 0.57 s | 113.4 tok/s | 323.7 tok/s |
| 8 | on | 0.58 s | 94.1 tok/s | 576.6 tok/s |
| 1 | off | 0.50 s | 153.9 tok/s | 108.4 tok/s |
| 2 | off | 0.55 s | 135.3 tok/s | 187.3 tok/s |
| 4 | off | 0.56 s | 114.7 tok/s | 331.2 tok/s |
| 8 | off | 0.58 s | 96.0 tok/s | 585.1 tok/s |

How to read it:

- **Batching works.** From 1 to 8 users, total throughput rises about 5.5× (105.5 to 576.6
  tok/s). Each request decodes more slowly as more share the GPU, about 40% slower (151.5 to
  94.1 tok/s), but nobody waits in a queue: the time to first token stays at about 0.5–0.6 s.
  The laptop engine in the README served one request at a time, so its time to first token grew
  with every extra user.
- **Prefix caching made no difference here.** The test sends one short fixed prompt, so there is
  almost nothing to reuse; on and off are within run-to-run noise. It should matter for
  multi-step agent runs, where every step resends the whole conversation so far. That is
  expected, not measured.
- These are indicative numbers for this one GPU and model.

## Lessons

**1. A port that Windows already uses cannot be served from WSL.** With WSL mirrored networking,
WSL and Windows share ports. A Windows process was already listening on the port planned for
vLLM, so vLLM could not use it. Adding the port to `ignoredPorts` in the WSL configuration let
vLLM bind, but loopback traffic to that port still went to the Windows process and the requests
timed out. The fix was to serve vLLM on another port and forward the public port to it.

**2. Thinking off breaks tool calls for this model.** With `enable_thinking: false` the chat
template opens an empty think block, and the model mostly writes something like "let me search"
and stops without calling a tool. The smoke test scored 58%. The template has no thinking budget,
so the agent runs use thinking on, with the output limit raised to 4,096 tokens. This makes the
latency not comparable with the laptop rows, which use reasoning off.

**3. Typographic characters can fail correct answers.** The model writes non-breaking hyphens
(U+2011) and narrow no-break spaces (U+202F), including as thousands separators ("110 634.5
kWh"). Correct citations such as `energy-management/EM-04_glossary.md`, written with non-breaking
hyphens, were removed as unverified, and correct figures and phrases were missed by the scorer. A user would have seen
correct sources stripped from the answer, so this was a fix to the agent as well as the scorer.
The citation check and scorer v3 now read these characters as plain hyphens and spaces.
Rescoring every stored earlier run changed zero verdicts. Details in the
[CHANGELOG](../CHANGELOG.md).

**4. Check the model's default sampling settings.** The model's `generation_config` sets
temperature 1.0, which vLLM uses when a request does not say otherwise. The agent's client sends
temperature 0.2 explicitly (`LLM_TEMPERATURE`), so the runs do not depend on the model's default.

**5. Do not size capacity from the first start.** Qwen3.6-27B in AWQ INT4 takes 18.3 GiB of
weights; GPU memory utilisation had to drop from 0.95 to 0.93 because WSL left less free memory
than 0.95 needs. On its first start vLLM reported a KV cache of 24,094 tokens at 16K and a 32K
start 0.1 GiB short of one request, so the runs used 16K. Restarted on 29 October with the same
settings, it reported 67,463 tokens at 16K (about 4 long requests at once) and 32K loaded too
(84,954 tokens). vLLM's start-up memory profiling had counted about 2.1 GiB more temporary
activation memory on the first start than on any later one, most likely a one-off from the first
run on the machine, and sized the KV cache down by that much. Qwen3-8B showed the same, smaller
effect (82,240 then 89,552 tokens); Nemotron did not. Restart once before quoting capacity. The
model fits at all because three of every four layers use linear attention (Gated DeltaNet), which
keeps no growing KV cache.

**6. Full defences still depend on the model.** Qwen3-8B appended an injected marker from a
held-out document whose instruction was written in Chinese, under all defences, and no security
event was logged. The larger models ignored the same text. Small models need the
injection tests run again, not assumed.

## Other models

Each was served alone on the same GPU and vLLM version, with thinking off (both Qwen models call
tools that way). Agent results are in the README.

| Model | Quant | Context | Parsers (tool / reasoning) | Configuration |
|---|---|---|---|---|
| Qwen3-8B (dense) | FP8 | 32,768 | `hermes` / `qwen3` | `vllm-4090-qwen3-8b` |
| Qwen3.6-27B (hybrid linear / full attention) | AWQ INT4 | 16,384 | `qwen3_coder` / `qwen3` | `vllm-4090-qwen3.6-27b` |

- **Qwen3-8B:** core 70% ± 2%, hard 62% ± 8%, median latency 2.1 s / 2.7 s.
- **Qwen3.6-27B:** core 94% ± 2%, hard 88% ± 6%, median latency 6.0 s / 11.8 s. KV cache 67,463
  tokens at 16K after a restart, about 4 long requests at once (24,094 on the first start; see
  Lesson 5). Re-run on the v2.0 system (`vllm-4090-qwen3.6-27b-v2`, same server settings):
  core 94% ± 2%, hard 91% ± 6%, median latency 6.1 s / 11.4 s.

**Embeddings.** Qwen3-Embedding-0.6B and bge-m3 (dense) were served by vLLM and used through
`EMBEDDING_PROVIDER=openai_compatible`, each with its own vector store. On the 10 retrieval
questions: Qwen3-Embedding-0.6B hit@1 90%, MRR 0.95 (the same as the default hash embedder);
bge-m3 hit@1 100%, MRR 1.00. The set is too easy to tell embedders apart.

## Next

- A harder retrieval set, so embedders can be compared.
- Injection tests in other languages, after the Qwen3-8B hold-out breach.
