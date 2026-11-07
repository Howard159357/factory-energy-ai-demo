# Inference profile: RTX 4090 / vLLM 0.30 / Nemotron 3.5 Lightning NVFP4 / prefix caching off

Generated 2026-10-28 19:07. One fixed prompt, streamed, temperature 0. Each user sends its requests back to back; all users start together. TTFT is the time to the first text token; decode speed is per request after the first token; throughput is all completion tokens over the wall time of the level. Indicative numbers for the hardware named in the title.

| Users | Requests | Errors | TTFT median (s) | TTFT max (s) | Decode tok/s per request (median) | Latency median (s) | Throughput tok/s (all users) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 0 | 0.50 | 0.50 | 153.9 | 1.7 | 108.4 |
| 2 | 6 | 0 | 0.55 | 0.77 | 135.3 | 2.0 | 187.3 |
| 4 | 12 | 0 | 0.56 | 0.60 | 114.7 | 2.2 | 331.2 |
| 8 | 24 | 0 | 0.58 | 0.63 | 96.0 | 2.5 | 585.1 |
