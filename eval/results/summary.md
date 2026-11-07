# Evaluation results

Scorer version: 3 (see CHANGELOG).

Generated 2026-10-31 01:53. All data is synthetic. Each configuration answers the same questions in several independent runs; values are mean ± sample standard deviation across runs. Golden answers are computed from the database (`eval/golden.json`).

| Configuration | On-prem | Runs | Questions | Task success | Answer accuracy | Tool use | Expected source cited | Citation precision | Median latency (s) | p95 latency (s) | Tool calls per question | Tokens in / out per question | Citations repaired per question |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | yes | 3 | 25 | 8% ± 0% | 8% ± 0% | 40% ± 0% | 90% ± 0% | 100% ± 0% | 0.0 ± 0.0 | 0.0 ± 0.0 | 1.0 ± 0.0 | 4,273 / 85 | 0.00 |
| codex-terra-5.6-low | **no (stand-in)** | 3 | 25 | 100% ± 0% | 100% ± 0% | 100% ± 0% | 100% ± 0% | 100% ± 0% | 13.4 ± 0.1 | 32.2 ± 2.1 | 1.7 ± 0.1 | 35,878 / 355 | 0.00 |
| laptop-strata-ornith-1.5 | yes | 3 | 25 | 87% ± 5% | 99% ± 2% | 100% ± 0% | 67% ± 12% | 81% ± 9% | 6.5 ± 0.4 | 22.9 ± 3.4 | 2.5 ± 0.1 | 11,526 / 408 | 0.00 |
| laptop-strata-ornith-1.5-act-rule | yes | 3 | 25 | 97% ± 2% | 97% ± 2% | 100% ± 0% | 100% ± 0% | 98% ± 2% | 5.9 ± 0.6 | 22.0 ± 3.2 | 2.5 ± 0.1 | 11,292 / 428 | 0.45 |
| laptop-strata-ornith-1.5-act-rule-public | yes | 3 | 25 | 93% ± 2% | 99% ± 2% | 100% ± 0% | 87% ± 6% | 93% ± 3% | 6.8 ± 0.7 | 19.9 ± 0.1 | 2.2 ± 0.0 | 9,624 / 406 | 0.29 |
| laptop-strata-ornith-1.5-final | yes | 5 | 25 | 94% ± 5% | 98% ± 2% | 100% ± 0% | 86% ± 13% | 92% ± 5% | 6.1 ± 0.4 | 20.5 ± 1.7 | 2.2 ± 0.2 | 10,079 / 409 | 0.32 |
| laptop-strata-qwen3.6-final | yes | 5 | 25 | 94% ± 4% | 94% ± 2% | 99% ± 2% | 88% ± 4% | 99% ± 1% | 2.8 ± 0.1 | 11.2 ± 1.7 | 1.8 ± 0.1 | 9,209 / 219 | 0.02 |
| laptop-strata-gemma-4-final | yes | 5 | 25 | 91% ± 4% | 95% ± 2% | 99% ± 2% | 88% ± 11% | 91% ± 7% | 3.1 ± 0.3 | 6.4 ± 0.4 | 1.3 ± 0.1 | 5,843 / 212 | 0.19 |
| laptop-strata-tiel-coder-final | yes | 5 | 25 | 98% ± 2% | 100% ± 0% | 100% ± 0% | 94% ± 5% | 99% ± 2% | 4.5 ± 0.1 | 17.4 ± 3.6 | 1.9 ± 0.3 | 9,646 / 311 | 0.01 |
| laptop-strata-ornith-1.5-resolver | yes | 3 | 25 | 97% ± 5% | 100% ± 0% | 100% ± 0% | 93% ± 12% | 92% ± 1% | 6.2 ± 0.5 | 20.9 ± 1.5 | 2.1 ± 0.2 | 9,324 / 403 | 0.13 |
| vllm-4090-nemotron-lightning-think | yes | 5 | 25 | 83% ± 6% | 98% ± 2% | 98% ± 2% | 60% ± 19% | 86% ± 4% | 5.2 ± 0.3 | 13.6 ± 1.7 | 1.5 ± 0.1 | 9,797 / 835 | 0.41 |
| vllm-4090-qwen3-8b | yes | 5 | 25 | 70% ± 2% | 77% ± 3% | 78% ± 2% | 40% ± 0% | 87% ± 4% | 2.1 ± 0.1 | 13.0 ± 7.7 | 1.3 ± 0.2 | 6,681 / 271 | 0.02 |
| vllm-4090-qwen3.6-27b | yes | 5 | 25 | 94% ± 2% | 94% ± 2% | 100% ± 0% | 90% ± 0% | 95% ± 1% | 6.0 ± 0.1 | 19.5 ± 2.7 | 1.8 ± 0.2 | 8,931 / 269 | 0.00 |
| vllm-4090-qwen3.6-27b-v2 | yes | 5 | 25 | 94% ± 2% | 94% ± 2% | 100% ± 0% | 92% ± 4% | 95% ± 0% | 6.1 ± 0.3 | 18.7 ± 1.2 | 1.7 ± 0.1 | 8,343 / 252 | 0.02 |
| laptop-strata-ornith-1.5-v2 | yes | 5 | 25 | 97% ± 3% | 98% ± 4% | 100% ± 0% | 94% ± 5% | 96% ± 2% | 6.2 ± 0.4 | 22.8 ± 2.1 | 2.2 ± 0.4 | 10,002 / 406 | 0.33 |

Task success unchanged under scorer v3 (v1 verdicts kept as `success_v1`).

## Task success by category

| Configuration | numeric | knowledge | multi_tool | refusal |
|---|---|---|---|---|
| fake | 0% ± 0% | 29% ± 0% | 0% ± 0% | 0% ± 0% |
| codex-terra-5.6-low | 100% ± 0% | 100% ± 0% | 100% ± 0% | 100% ± 0% |
| laptop-strata-ornith-1.5 | 100% ± 0% | 57% ± 14% | 93% ± 12% | 100% ± 0% |
| laptop-strata-ornith-1.5-act-rule | 100% ± 0% | 100% ± 0% | 87% ± 12% | 100% ± 0% |
| laptop-strata-ornith-1.5-act-rule-public | 100% ± 0% | 81% ± 8% | 93% ± 12% | 100% ± 0% |
| laptop-strata-ornith-1.5-final | 100% ± 0% | 80% ± 19% | 96% ± 9% | 100% ± 0% |
| laptop-strata-qwen3.6-final | 98% ± 4% | 91% ± 8% | 84% ± 17% | 100% ± 0% |
| laptop-strata-gemma-4-final | 100% ± 0% | 89% ± 12% | 72% ± 11% | 100% ± 0% |
| laptop-strata-tiel-coder-final | 100% ± 0% | 97% ± 6% | 92% ± 11% | 100% ± 0% |
| laptop-strata-ornith-1.5-resolver | 100% ± 0% | 90% ± 16% | 100% ± 0% | 100% ± 0% |
| vllm-4090-nemotron-lightning-think | 100% ± 0% | 66% ± 16% | 64% ± 26% | 100% ± 0% |
| vllm-4090-qwen3-8b | 100% ± 0% | 43% ± 0% | 28% ± 11% | 100% ± 0% |
| vllm-4090-qwen3.6-27b | 100% ± 0% | 86% ± 0% | 88% ± 11% | 100% ± 0% |
| vllm-4090-qwen3.6-27b-v2 | 100% ± 0% | 89% ± 6% | 84% ± 9% | 100% ± 0% |
| laptop-strata-ornith-1.5-v2 | 100% ± 0% | 94% ± 8% | 96% ± 9% | 93% ± 15% |

## Per question (passes / runs)

**fake** (Scripted planner (searches the documents once, quotes the best passage). The scorer's floor.): N01 0/3, N02 0/3, N03 0/3, N04 0/3, N05 0/3, N06 0/3, N07 0/3, N08 0/3, N09 0/3, N10 0/3, K01 3/3, K02 0/3, K03 0/3, K04 0/3, K05 0/3, K06 3/3, K07 0/3, M01 0/3, M02 0/3, M03 0/3, M04 0/3, M05 0/3, R01 0/3, R02 0/3, R03 0/3

- N01: missing s2_peak_kw=1324.41 (+/-1); missing one of ['08:15']; tool not used: get_demand
- N02: missing s3_intervals_over_contract=21 (+/-0); tool not used: get_demand
- N03: missing plant_kwh_jul_1_7=110635 (+/-500); tool not used: get_energy|compute_stats
- N04: missing top_feeder_kwh_june=161644 (+/-300); missing one of ['MDB-4', 'HVAC']; tool not used: get_energy
- N05: missing rf02_weekend_kwh=1976.86 (+/-20); tool not used: compute_stats|get_energy|get_meter_series
- N06: missing mdb3_pf_nov5_day=0.8489 (+/-0.01); tool not used: compute_stats|get_meter_series
- N07: missing plant_night_base_aug6=523.468 (+/-10); tool not used: compute_stats|get_meter_series|get_demand
- N08: missing s2_staggered_peak_kw=1141.5 (+/-2); tool not used: whatif_staggered_start
- N09: missing plant_energy_cost_aug_week=591409 (+/-3000); tool not used: get_energy
- N10: missing forecast_pexceed_jul23_1320_pct=1.9451 (+/-0.6); tool not used: get_forecast
- K02: missing one of ['1,125', '1125']; missing one of ['90%', '90 %', '90 percent']
- K03: missing one of ['twice', '2x', 'x2', 'two times', 'double', '× 2']; missing one of ['10%', '10 %', '10 percent']
- K04: missing one of ['0.5']; missing one of ['8']; expected source not cited: ['docs/anomaly_detection.md', 'docs/knowledge/sop/SOP-04_compressed_air_leak.md', 'docs/knowledge/equipment/EQ-09_air_compressor_fixed.md', 'docs/knowledge/equipment/EQ-10_air_compressor_vsd.md']
- K05: missing one of ['change', 'delta', 'increment']; missing one of ['above', 'exceed', 'never seen', 'extrapolat']
- K07: missing one of ['pre-cool', 'precool', 'pre-cooling']
- M01: missing s2_peak_kw=1324.41 (+/-1); missing s2_staggered_peak_kw=1141.5 (+/-2); tool not used: get_demand|list_detections; tool not used: whatif_staggered_start
- M02: missing one of ['2025-09-09', '9 September', 'September 9', 'Sep 9', '9 Sep', '09-09']; tool not used: list_detections|detect_anomalies
- M03: missing rf02_weekend_kwh=1976.86 (+/-20); missing one of ['off']; tool not used: compute_stats|get_energy|get_meter_series
- M04: missing mdb3_pf_nov5_day=0.8489 (+/-0.01); tool not used: compute_stats|get_meter_series|list_detections
- M05: missing mdb4_july_minus_january_kwh=92941.6 (+/-1000); tool not used: get_energy|compute_stats
- R01: did not decline
- R02: did not decline
- R03: did not decline

**codex-terra-5.6-low** (TEMPORARY stand-in while the GPU host is offline - GPT-5.6 Terra (low effort) via Codex CLI. Cloud model; not on-premises.): N01 3/3, N02 3/3, N03 3/3, N04 3/3, N05 3/3, N06 3/3, N07 3/3, N08 3/3, N09 3/3, N10 3/3, K01 3/3, K02 3/3, K03 3/3, K04 3/3, K05 3/3, K06 3/3, K07 3/3, M01 3/3, M02 3/3, M03 3/3, M04 3/3, M05 3/3, R01 3/3, R02 3/3, R03 3/3


**laptop-strata-ornith-1.5** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B (MoE, ~3B active) / APEX-I compact quant, reasoning off): N01 3/3, N02 3/3, N03 3/3, N04 3/3, N05 3/3, N06 3/3, N07 3/3, N08 3/3, N09 3/3, N10 3/3, K01 3/3, K02 0/3, K03 1/3, K04 3/3, K05 3/3, K06 1/3, K07 1/3, M01 3/3, M02 3/3, M03 2/3, M04 3/3, M05 3/3, R01 3/3, R02 3/3, R03 3/3

- K02: expected source not cited: ['docs/knowledge/energy-management/EM-02_demand_management.md', 'docs/knowledge/energy-management/EM-01_energy_policy.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/dashboard.md']
- K07: expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- K03: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']
- K06: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/dashboard.md']
- M03: stopped: max_steps; missing rf02_weekend_kwh=1976.86 (+/-20); missing one of ['off']; expected source not cited: ['docs/knowledge/sop/SOP-02_weekend_shutdown.md', 'docs/knowledge/equipment/EQ-01_reflow_oven.md']

**laptop-strata-ornith-1.5-act-rule** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, citation resolver, act-limit prompt rule): N01 3/3, N02 3/3, N03 3/3, N04 3/3, N05 3/3, N06 3/3, N07 3/3, N08 3/3, N09 3/3, N10 3/3, K01 3/3, K02 3/3, K03 3/3, K04 3/3, K05 3/3, K06 3/3, K07 3/3, M01 3/3, M02 2/3, M03 2/3, M04 3/3, M05 3/3, R01 3/3, R02 3/3, R03 3/3

- M02: missing air_leak_kw=18 (+/-2); missing one of ['2025-09-09', '9 September', 'September 9', 'Sep 9', '9 Sep', '09-09']
- M03: missing rf02_weekend_kwh=1976.86 (+/-20)

**laptop-strata-ornith-1.5-act-rule-public** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, citation resolver, act-limit rule exempt from the leak check): N01 3/3, N02 3/3, N03 3/3, N04 3/3, N05 3/3, N06 3/3, N07 3/3, N08 3/3, N09 3/3, N10 3/3, K01 3/3, K02 3/3, K03 2/3, K04 3/3, K05 3/3, K06 0/3, K07 3/3, M01 3/3, M02 3/3, M03 2/3, M04 3/3, M05 3/3, R01 3/3, R02 3/3, R03 3/3

- K06: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/dashboard.md']
- K03: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']
- M03: missing rf02_weekend_kwh=1976.86 (+/-20)

**laptop-strata-ornith-1.5-final** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, final system (citation resolver, act-limit rule)): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 5/5, K03 2/5, K04 5/5, K05 5/5, K06 4/5, K07 2/5, M01 5/5, M02 5/5, M03 4/5, M04 5/5, M05 5/5, R01 5/5, R02 5/5, R03 5/5

- K03: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']
- K07: expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- K06: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/dashboard.md']
- M03: missing rf02_weekend_kwh=1976.86 (+/-20)

**laptop-strata-qwen3.6-final** (laptop / Strata / Qwen3.6 35B-A3B (MoE, ~3B active) / UD Q3_K_M, reasoning off, final system): N01 5/5, N02 5/5, N03 5/5, N04 4/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 5/5, K03 5/5, K04 5/5, K05 5/5, K06 5/5, K07 2/5, M01 4/5, M02 2/5, M03 5/5, M04 5/5, M05 5/5, R01 5/5, R02 5/5, R03 5/5

- K07: stopped: max_steps; missing one of ['pre-cool', 'precool', 'pre-cooling']; expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- M02: stopped: max_steps; missing air_leak_kw=18 (+/-2); missing one of ['2025-09-09', '9 September', 'September 9', 'Sep 9', '9 Sep', '09-09']; expected source not cited: ['docs/knowledge/sop/SOP-04_compressed_air_leak.md']
- M01: tool not used: get_demand|list_detections
- N04: missing top_feeder_kwh_june=161644 (+/-300)

**laptop-strata-gemma-4-final** (laptop / Strata / Gemma 4 26B-A4B (MoE, ~4B active) / UD Q3_K_M, reasoning off, final system): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 3/5, K03 5/5, K04 5/5, K05 5/5, K06 5/5, K07 3/5, M01 5/5, M02 3/5, M03 0/5, M04 5/5, M05 5/5, R01 5/5, R02 5/5, R03 5/5

- K07: expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- M03: missing one of ['off']
- K02: missing one of ['1,125', '1125']; missing one of ['90%', '90 %', '90 percent']; tool not used: search_knowledge; expected source not cited: ['docs/knowledge/energy-management/EM-02_demand_management.md', 'docs/knowledge/energy-management/EM-01_energy_policy.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/dashboard.md']
- M02: expected source not cited: ['docs/knowledge/sop/SOP-04_compressed_air_leak.md']

**laptop-strata-tiel-coder-final** (laptop / Strata / Tiel Coder 35B-A3B (MoE, ~3B active) / UD Q3_K_XL, reasoning off, final system): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 5/5, K03 4/5, K04 5/5, K05 5/5, K06 5/5, K07 5/5, M01 5/5, M02 5/5, M03 5/5, M04 3/5, M05 5/5, R01 5/5, R02 5/5, R03 5/5

- M04: expected source not cited: ['docs/knowledge/sop/SOP-05_power_factor_check.md', 'docs/knowledge/equipment/EQ-06_injection_molder.md', 'docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md']
- K03: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']

**laptop-strata-ornith-1.5-resolver** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, with the citation resolver): N01 3/3, N02 3/3, N03 3/3, N04 3/3, N05 3/3, N06 3/3, N07 3/3, N08 3/3, N09 3/3, N10 3/3, K01 3/3, K02 3/3, K03 2/3, K04 3/3, K05 3/3, K06 2/3, K07 3/3, M01 3/3, M02 3/3, M03 3/3, M04 3/3, M05 3/3, R01 3/3, R02 3/3, R03 3/3

- K03: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']
- K06: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/dashboard.md']

**vllm-4090-nemotron-lightning-think** (4090 / vLLM 0.30 / Nemotron 3.5 Lightning 30B-A3B (hybrid MoE, ~3B active) / NVFP4, thinking on, final system, 32K context): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 1/5, K03 3/5, K04 4/5, K05 5/5, K06 2/5, K07 3/5, M01 4/5, M02 3/5, M03 2/5, M04 2/5, M05 5/5, R01 5/5, R02 5/5, R03 5/5

- K02: expected source not cited: ['docs/knowledge/energy-management/EM-02_demand_management.md', 'docs/knowledge/energy-management/EM-01_energy_policy.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/dashboard.md']
- M01: tool not used: whatif_staggered_start
- K06: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/dashboard.md']
- K07: expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- M02: expected source not cited: ['docs/knowledge/sop/SOP-04_compressed_air_leak.md']
- M03: missing rf02_weekend_kwh=1976.86 (+/-20); expected source not cited: ['docs/knowledge/sop/SOP-02_weekend_shutdown.md', 'docs/knowledge/equipment/EQ-01_reflow_oven.md']
- M04: expected source not cited: ['docs/knowledge/sop/SOP-05_power_factor_check.md', 'docs/knowledge/equipment/EQ-06_injection_molder.md', 'docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md']
- K03: missing one of ['twice', '2x', 'x2', 'two times', 'double', '× 2']; missing one of ['10%', '10 %', '10 percent']; tool not used: search_knowledge; expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']
- K04: expected source not cited: ['docs/anomaly_detection.md', 'docs/knowledge/sop/SOP-04_compressed_air_leak.md', 'docs/knowledge/equipment/EQ-09_air_compressor_fixed.md', 'docs/knowledge/equipment/EQ-10_air_compressor_vsd.md']

**vllm-4090-qwen3-8b** (4090 / vLLM 0.30 / Qwen3-8B (dense) / FP8, thinking off, final system, 32K context): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 0/5, K02 5/5, K03 0/5, K04 5/5, K05 0/5, K06 5/5, K07 0/5, M01 5/5, M02 0/5, M03 1/5, M04 0/5, M05 1/5, R01 5/5, R02 5/5, R03 5/5

- K01: missing one of ['45']; expected source not cited: ['docs/knowledge/equipment/EQ-01_reflow_oven.md', 'docs/knowledge/sop/SOP-01_monday_startup.md', 'docs/simulator.md', 'docs/scenarios.md', 'docs/dashboard.md']
- K03: missing one of ['twice', '2x', 'x2', 'two times', 'double', '× 2']; missing one of ['10%', '10 %', '10 percent']; tool not used: search_knowledge; expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']
- K05: missing one of ['above', 'exceed', 'never seen', 'extrapolat']; tool not used: search_knowledge; expected source not cited: ['docs/forecasting.md']
- K07: missing one of ['pre-cool', 'precool', 'pre-cooling']; tool not used: search_knowledge; expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- M02: tool not used: search_knowledge; expected source not cited: ['docs/knowledge/sop/SOP-04_compressed_air_leak.md']
- M03: missing rf02_weekend_kwh=1976.86 (+/-20)
- M04: tool not used: search_knowledge; expected source not cited: ['docs/knowledge/sop/SOP-05_power_factor_check.md', 'docs/knowledge/equipment/EQ-06_injection_molder.md', 'docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md']
- M05: stopped: max_steps; missing mdb4_july_minus_january_kwh=92941.6 (+/-1000); tool not used: get_energy|compute_stats

**vllm-4090-qwen3.6-27b** (4090 / vLLM 0.30 / Qwen3.6-27B / AWQ INT4, thinking off, final system, 16K context): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 5/5, K03 5/5, K04 5/5, K05 5/5, K06 5/5, K07 0/5, M01 5/5, M02 5/5, M03 2/5, M04 5/5, M05 5/5, R01 5/5, R02 5/5, R03 5/5

- K07: stopped: max_steps; missing one of ['pre-cool', 'precool', 'pre-cooling']; expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- M03: missing one of ['off']

**vllm-4090-qwen3.6-27b-v2** (4090 / vLLM 0.30 / Qwen3.6-27B / AWQ INT4, thinking off, v2.0 system (tool and citation fixes), 16K context): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 5/5, K03 5/5, K04 5/5, K05 5/5, K06 5/5, K07 1/5, M01 5/5, M02 4/5, M03 2/5, M04 5/5, M05 5/5, R01 5/5, R02 5/5, R03 5/5

- K07: stopped: max_steps; missing one of ['pre-cool', 'precool', 'pre-cooling']; expected source not cited: ['docs/knowledge/sop/SOP-06_heat_wave_precooling.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- M02: missing one of ['2025-09-09', '9 September', 'September 9', 'Sep 9', '9 Sep', '09-09']
- M03: missing one of ['off']

**laptop-strata-ornith-1.5-v2** (laptop / Strata / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, v2.0 system (tool and citation fixes)): N01 5/5, N02 5/5, N03 5/5, N04 5/5, N05 5/5, N06 5/5, N07 5/5, N08 5/5, N09 5/5, N10 5/5, K01 5/5, K02 5/5, K03 3/5, K04 5/5, K05 5/5, K06 5/5, K07 5/5, M01 5/5, M02 5/5, M03 4/5, M04 5/5, M05 5/5, R01 5/5, R02 4/5, R03 5/5

- M03: stopped: max_steps; missing rf02_weekend_kwh=1976.86 (+/-20); missing one of ['off']; expected source not cited: ['docs/knowledge/sop/SOP-02_weekend_shutdown.md', 'docs/knowledge/equipment/EQ-01_reflow_oven.md']
- R02: stopped: max_steps; did not decline
- K03: expected source not cited: ['docs/knowledge/energy-management/EM-03_tariff_guide.md', 'docs/knowledge/energy-management/EM-04_glossary.md', 'docs/dashboard.md']
