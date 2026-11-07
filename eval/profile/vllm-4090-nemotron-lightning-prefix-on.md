# Inference profile: RTX 4090 / vLLM 0.30 / Nemotron 3.5 Lightning NVFP4 / prefix caching on

Generated 2026-10-28 19:02. One fixed prompt, streamed, temperature 0. Each user sends its requests back to back; all users start together. TTFT is the time to the first text token; decode speed is per request after the first token; throughput is all completion tokens over the wall time of the level. Indicative numbers for the hardware named in the title.

| Users | Requests | Errors | TTFT median (s) | TTFT max (s) | Decode tok/s per request (median) | Latency median (s) | Throughput tok/s (all users) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 0 | 0.50 | 0.55 | 151.5 | 1.7 | 105.5 |
| 2 | 6 | 0 | 0.54 | 0.80 | 131.9 | 2.0 | 182.0 |
| 4 | 12 | 0 | 0.57 | 0.59 | 113.4 | 2.2 | 323.7 |
| 8 | 24 | 0 | 0.58 | 0.61 | 94.1 | 2.5 | 576.6 |
