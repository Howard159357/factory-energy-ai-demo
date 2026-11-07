# Inference profile: laptop RTX 3080 16 GB / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, called over Tailscale

Generated 2026-10-24 01:53. One fixed prompt, streamed, temperature 0. Each user sends its requests back to back; all users start together. TTFT is the time to the first text token; decode speed is per request after the first token; throughput is all completion tokens over the wall time of the level. Indicative numbers for the hardware named in the title.

| Users | Requests | Errors | TTFT median (s) | TTFT max (s) | Decode tok/s per request (median) | Latency median (s) | Throughput tok/s (all users) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 0 | 0.04 | 0.04 | 79.6 | 3.2 | 78.0 |
| 2 | 6 | 0 | 3.04 | 3.10 | 85.2 | 5.9 | 84.8 |
| 4 | 12 | 0 | 9.09 | 9.52 | 83.1 | 12.2 | 83.2 |
