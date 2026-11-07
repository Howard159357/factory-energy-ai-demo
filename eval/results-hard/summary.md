# Evaluation results: hard questions (X set)

Scorer version: 3 (see CHANGELOG).

Generated 2026-10-31 01:53. All data is synthetic. Each configuration answers the same questions in several independent runs; values are mean ± sample standard deviation across runs. Golden answers are computed from the database (`eval/golden.json`).

| Configuration | On-prem | Runs | Questions | Task success | Answer accuracy | Tool use | Expected source cited | Citation precision | Median latency (s) | p95 latency (s) | Tool calls per question | Tokens in / out per question | Citations repaired per question |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | yes | 3 | 10 | 10% ± 0% | 10% ± 0% | 70% ± 0% | 100% ± 0% | 100% ± 0% | 0.0 ± 0.0 | 0.5 ± 0.8 | 1.0 ± 0.0 | 4,688 / 80 | 0.00 |
| laptop-strata-ornith-1.5 | yes | 3 | 10 | 77% ± 6% | 77% ± 6% | 100% ± 0% | 83% ± 29% | 74% ± 4% | 12.0 ± 0.4 | 33.2 ± 15.4 | 2.9 ± 0.2 | 11,039 / 532 | 0.00 |
| laptop-strata-ornith-1.5-act-rule | yes | 3 | 10 | 93% ± 12% | 93% ± 12% | 100% ± 0% | 100% ± 0% | 93% ± 6% | 9.6 ± 0.8 | 16.8 ± 3.9 | 2.4 ± 0.5 | 10,006 / 465 | 0.43 |
| laptop-strata-ornith-1.5-final | yes | 10 | 10 | 88% ± 8% | 89% ± 7% | 100% ± 0% | 95% ± 16% | 94% ± 5% | 9.7 ± 0.8 | 17.6 ± 5.8 | 2.8 ± 0.8 | 11,191 / 500 | 0.45 |
| laptop-strata-qwen3.6-final | yes | 10 | 10 | 89% ± 6% | 89% ± 6% | 100% ± 0% | 95% ± 16% | 87% ± 5% | 5.2 ± 0.6 | 9.5 ± 1.6 | 1.6 ± 0.3 | 8,317 / 251 | 0.02 |
| laptop-strata-gemma-4-final | yes | 10 | 10 | 65% ± 5% | 65% ± 5% | 100% ± 0% | 45% ± 16% | 88% ± 9% | 5.6 ± 0.3 | 10.9 ± 0.9 | 2.7 ± 0.1 | 11,793 / 287 | 0.20 |
| laptop-strata-tiel-coder-final | yes | 10 | 10 | 94% ± 8% | 94% ± 8% | 100% ± 0% | 100% ± 0% | 99% ± 3% | 7.7 ± 0.6 | 12.4 ± 2.1 | 2.3 ± 0.2 | 9,923 / 383 | 0.16 |
| laptop-strata-ornith-1.5-resolver | yes | 3 | 10 | 80% ± 0% | 80% ± 0% | 100% ± 0% | 100% ± 0% | 91% ± 10% | 10.7 ± 0.6 | 20.1 ± 3.1 | 3.3 ± 0.2 | 13,294 / 574 | 0.33 |
| vllm-4090-nemotron-lightning-think | yes | 10 | 10 | 78% ± 6% | 83% ± 7% | 99% ± 3% | 70% ± 26% | 86% ± 10% | 10.7 ± 1.4 | 34.1 ± 4.7 | 3.0 ± 0.4 | 18,559 / 1,762 | 0.43 |
| vllm-4090-qwen3-8b | yes | 10 | 10 | 62% ± 8% | 62% ± 8% | 99% ± 3% | 95% ± 16% | 86% ± 0% | 2.7 ± 0.4 | 11.2 ± 3.1 | 1.6 ± 0.3 | 7,133 / 224 | 0.10 |
| vllm-4090-qwen3.6-27b | yes | 10 | 10 | 88% ± 6% | 89% ± 6% | 100% ± 0% | 95% ± 16% | 83% ± 4% | 11.8 ± 0.9 | 45.1 ± 13.4 | 1.9 ± 0.1 | 9,484 / 512 | 0.43 |
| vllm-4090-qwen3.6-27b-v2 | yes | 10 | 10 | 91% ± 6% | 92% ± 6% | 100% ± 0% | 90% ± 21% | 81% ± 6% | 11.4 ± 0.9 | 42.0 ± 22.2 | 1.9 ± 0.1 | 9,731 / 494 | 0.50 |
| laptop-strata-ornith-1.5-v2 | yes | 10 | 10 | 93% ± 7% | 93% ± 7% | 100% ± 0% | 100% ± 0% | 98% ± 3% | 10.1 ± 0.6 | 19.0 ± 8.0 | 2.4 ± 0.2 | 10,040 / 491 | 0.30 |

Task success unchanged under scorer v3 (v1 verdicts kept as `success_v1`).

## Task success by category

| Configuration | chain | scope | limits | ambiguous | citation |
|---|---|---|---|---|---|
| fake | 0% ± 0% | 0% ± 0% | 0% ± 0% | 0% ± 0% | 50% ± 0% |
| laptop-strata-ornith-1.5 | 67% ± 29% | 50% ± 0% | 100% ± 0% | 83% ± 29% | 83% ± 29% |
| laptop-strata-ornith-1.5-act-rule | 83% ± 29% | 100% ± 0% | 100% ± 0% | 83% ± 29% | 100% ± 0% |
| laptop-strata-ornith-1.5-final | 95% ± 16% | 85% ± 24% | 95% ± 16% | 70% ± 35% | 95% ± 16% |
| laptop-strata-qwen3.6-final | 90% ± 21% | 100% ± 0% | 100% ± 0% | 60% ± 21% | 95% ± 16% |
| laptop-strata-gemma-4-final | 60% ± 21% | 100% ± 0% | 100% ± 0% | 50% ± 0% | 15% ± 24% |
| laptop-strata-tiel-coder-final | 95% ± 16% | 100% ± 0% | 100% ± 0% | 80% ± 26% | 95% ± 16% |
| laptop-strata-ornith-1.5-resolver | 100% ± 0% | 50% ± 0% | 100% ± 0% | 50% ± 0% | 100% ± 0% |
| vllm-4090-nemotron-lightning-think | 90% ± 21% | 90% ± 21% | 100% ± 0% | 50% ± 0% | 60% ± 21% |
| vllm-4090-qwen3-8b | 55% ± 28% | 100% ± 0% | 50% ± 0% | 50% ± 0% | 55% ± 16% |
| vllm-4090-qwen3.6-27b | 100% ± 0% | 100% ± 0% | 100% ± 0% | 55% ± 16% | 85% ± 24% |
| vllm-4090-qwen3.6-27b-v2 | 100% ± 0% | 100% ± 0% | 100% ± 0% | 65% ± 24% | 90% ± 21% |
| laptop-strata-ornith-1.5-v2 | 95% ± 16% | 100% ± 0% | 95% ± 16% | 75% ± 26% | 100% ± 0% |

## Per question (passes / runs)

**fake** (Scripted planner (searches the documents once, quotes the best passage). The scorer's floor.): X01 0/3, X02 0/3, X03 0/3, X04 0/3, X05 0/3, X06 0/3, X07 0/3, X08 0/3, X09 0/3, X10 3/3

- X01: missing mdb5_kwh_sep9_15=21605.2 (+/-220); missing mdb5_kwh_sep2_8=20697.2 (+/-210); tool not used: list_detections|detect_anomalies; tool not used: get_energy|compute_stats
- X02: missing mdb3_pf_nov3_day=0.8616 (+/-0.01); tool not used: list_detections|detect_anomalies; tool not used: compute_stats|get_meter_series
- X03: did not decline
- X04: did not decline
- X05: no alternative matched: missing plant_kwh_q3=1.4919e+06 (+/-15000) | missing one of ['31']; missing one of ['month', 'split', 'separate', 'smaller', 'window', 'part']
- X06: missing one of ['2025']; did not decline
- X07: neither asked for clarification nor stated an assumption
- X08: missing s2_peak_kw=1324.41 (+/-1); missing one of ['contract', '1,250', '1250']; tool not used: get_demand
- X09: missing one of ['1,210', '1210']

**laptop-strata-ornith-1.5** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B (MoE, ~3B active) / APEX-I compact quant, reasoning off): X01 1/3, X02 3/3, X03 3/3, X04 0/3, X05 3/3, X06 3/3, X07 2/3, X08 3/3, X09 3/3, X10 2/3

- X04: did not decline
- X07: neither asked for clarification nor stated an assumption
- X01: missing mdb5_kwh_sep9_15=21605.2 (+/-220); missing mdb5_kwh_sep2_8=20697.2 (+/-210)
- X10: cited what it did not retrieve: ['source:EM-02 Demand Management > Load-shed playbook', 'source:EQ-12 Server Room Manual', 'source:EM-02 Demand Management > Load-shed playbook > Never shed']; expected source not cited: ['docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']

**laptop-strata-ornith-1.5-act-rule** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, citation resolver, act-limit prompt rule): X01 2/3, X02 3/3, X03 3/3, X04 3/3, X05 3/3, X06 3/3, X07 2/3, X08 3/3, X09 3/3, X10 3/3

- X01: missing mdb5_kwh_sep9_15=21605.2 (+/-220)
- X07: neither asked for clarification nor stated an assumption

**laptop-strata-ornith-1.5-final** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, final system (citation resolver, act-limit rule)): X01 9/10, X02 10/10, X03 7/10, X04 10/10, X05 10/10, X06 9/10, X07 5/10, X08 9/10, X09 9/10, X10 10/10

- X07: neither asked for clarification nor stated an assumption
- X03: stopped: max_steps; did not decline
- X09: expected source not cited: ['docs/knowledge/sop/SOP-02_weekend_shutdown.md', 'docs/knowledge/equipment/EQ-01_reflow_oven.md']
- X08: stopped: max_steps; missing s2_peak_kw=1324.41 (+/-1); missing one of ['contract', '1,250', '1250']
- X01: missing mdb5_kwh_sep2_8=20697.2 (+/-210)
- X06: missing one of ['2025']

**laptop-strata-qwen3.6-final** (laptop / Strata / Qwen3.6 35B-A3B (MoE, ~3B active) / UD Q3_K_M, reasoning off, final system): X01 8/10, X02 10/10, X03 10/10, X04 10/10, X05 10/10, X06 10/10, X07 2/10, X08 10/10, X09 10/10, X10 9/10

- X01: missing mdb5_kwh_sep9_15=21605.2 (+/-220); missing mdb5_kwh_sep2_8=20697.2 (+/-210)
- X07: neither asked for clarification nor stated an assumption
- X10: stopped: max_steps; missing one of ['EV']; missing one of ['server']; expected source not cited: ['docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']

**laptop-strata-gemma-4-final** (laptop / Strata / Gemma 4 26B-A4B (MoE, ~4B active) / UD Q3_K_M, reasoning off, final system): X01 2/10, X02 10/10, X03 10/10, X04 10/10, X05 10/10, X06 10/10, X07 0/10, X08 10/10, X09 3/10, X10 0/10

- X01: missing mdb5_kwh_sep9_15=21605.2 (+/-220)
- X07: neither asked for clarification nor stated an assumption
- X10: stopped: max_steps; missing one of ['EV']; missing one of ['server']; expected source not cited: ['docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- X09: missing one of ['1,210', '1210']

**laptop-strata-tiel-coder-final** (laptop / Strata / Tiel Coder 35B-A3B (MoE, ~3B active) / UD Q3_K_XL, reasoning off, final system): X01 9/10, X02 10/10, X03 10/10, X04 10/10, X05 10/10, X06 10/10, X07 6/10, X08 10/10, X09 10/10, X10 9/10

- X07: neither asked for clarification nor stated an assumption
- X01: missing mdb5_kwh_sep9_15=21605.2 (+/-220); missing mdb5_kwh_sep2_8=20697.2 (+/-210)
- X10: cited what it did not retrieve: ['source:docs/knowledge/energy-management/EM-02_demand_management.md#SOP-03 Demand Exceedance Response > Step 2: shed in playbook order']

**laptop-strata-ornith-1.5-resolver** (laptop / Strata 0.1.45 / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, with the citation resolver): X01 3/3, X02 3/3, X03 3/3, X04 0/3, X05 3/3, X06 3/3, X07 0/3, X08 3/3, X09 3/3, X10 3/3

- X04: did not decline
- X07: neither asked for clarification nor stated an assumption

**vllm-4090-nemotron-lightning-think** (4090 / vLLM 0.30 / Nemotron 3.5 Lightning 30B-A3B (hybrid MoE, ~3B active) / NVFP4, thinking on, final system, 32K context): X01 9/10, X02 9/10, X03 9/10, X04 9/10, X05 10/10, X06 10/10, X07 0/10, X08 10/10, X09 7/10, X10 5/10

- X07: neither asked for clarification nor stated an assumption
- X09: cited what it did not retrieve: ['source:same passage']
- X10: expected source not cited: ['docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- X03: stopped: max_steps; did not decline
- X01: stopped: max_steps; missing mdb5_kwh_sep9_15=21605.2 (+/-220); missing mdb5_kwh_sep2_8=20697.2 (+/-210)
- X02: tool not used: list_detections|detect_anomalies
- X04: stopped: max_steps; did not decline

**vllm-4090-qwen3-8b** (4090 / vLLM 0.30 / Qwen3-8B (dense) / FP8, thinking off, final system, 32K context): X01 8/10, X02 3/10, X03 10/10, X04 10/10, X05 0/10, X06 10/10, X07 0/10, X08 10/10, X09 10/10, X10 1/10

- X02: missing mdb3_pf_nov3_day=0.8616 (+/-0.01)
- X05: no alternative matched: missing plant_kwh_q3=1.4919e+06 (+/-15000) | missing one of ['31']; missing one of ['month', 'split', 'separate', 'smaller', 'window', 'part']
- X07: neither asked for clarification nor stated an assumption
- X10: missing one of ['server']; expected source not cited: ['docs/knowledge/sop/SOP-03_demand_exceedance_response.md', 'docs/knowledge/energy-management/EM-02_demand_management.md']
- X01: stopped: max_steps; missing mdb5_kwh_sep9_15=21605.2 (+/-220); missing mdb5_kwh_sep2_8=20697.2 (+/-210); tool not used: get_energy|compute_stats

**vllm-4090-qwen3.6-27b** (4090 / vLLM 0.30 / Qwen3.6-27B / AWQ INT4, thinking off, final system, 16K context): X01 10/10, X02 10/10, X03 10/10, X04 10/10, X05 10/10, X06 10/10, X07 1/10, X08 10/10, X09 7/10, X10 10/10

- X07: neither asked for clarification nor stated an assumption
- X09: expected source not cited: ['docs/knowledge/sop/SOP-02_weekend_shutdown.md', 'docs/knowledge/equipment/EQ-01_reflow_oven.md']

**vllm-4090-qwen3.6-27b-v2** (4090 / vLLM 0.30 / Qwen3.6-27B / AWQ INT4, thinking off, v2.0 system (tool and citation fixes), 16K context): X01 10/10, X02 10/10, X03 10/10, X04 10/10, X05 10/10, X06 10/10, X07 3/10, X08 10/10, X09 8/10, X10 10/10

- X07: neither asked for clarification nor stated an assumption
- X09: stopped: llm_error; missing one of ['1,210', '1210']; missing one of ['standby']; expected source not cited: ['docs/knowledge/sop/SOP-02_weekend_shutdown.md', 'docs/knowledge/equipment/EQ-01_reflow_oven.md']

**laptop-strata-ornith-1.5-v2** (laptop / Strata / Ornith 1.5 35B-A3B / APEX-I compact, reasoning off, v2.0 system (tool and citation fixes)): X01 9/10, X02 10/10, X03 10/10, X04 10/10, X05 10/10, X06 9/10, X07 5/10, X08 10/10, X09 10/10, X10 10/10

- X07: neither asked for clarification nor stated an assumption
- X01: missing mdb5_kwh_sep9_15=21605.2 (+/-220); missing mdb5_kwh_sep2_8=20697.2 (+/-210)
- X06: missing one of ['2025']
