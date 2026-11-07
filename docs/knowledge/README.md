# DemoTronics Knowledge Corpus

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## What this folder is

This folder holds a generated corpus of Markdown documents for the fictional DemoTronics Electronics Plant. The documents are indexed by the RAG knowledge base of the factory energy demo and are cited by the agent when it answers questions.

All content is synthetic. No real company, product, person or site is described. The only real reference is that the tariff follows the published high-voltage three-segment time-of-use structure, which is stated in the tariff guide.

The numbers in these documents match `config/meters.yaml` and `config/factory.yaml`. Where a document derives a figure from a rating and a share (for example kW from a percentage), the derivation uses those configured values.

## Licence

The documents are released under the repository's MIT licence.

## Document conventions

Each document starts with a title, a one-line synthetic notice and a document control table with the document ID, revision, owner role and the equipment or area it applies to. Owners are named by role, not by person.

## Contents

### energy-management

| ID | File | Subject |
|---|---|---|
| EM-01 | energy-management/EM-01_energy_policy.md | Energy policy, objectives, roles, review cadence |
| EM-02 | energy-management/EM-02_demand_management.md | 15-minute demand, alarm tiers, projection, load-shed playbook |
| EM-03 | energy-management/EM-03_tariff_guide.md | Time-of-use prices, demand charges, exceedance, power factor, leak cost |
| EM-04 | energy-management/EM-04_glossary.md | Glossary of terms |

### equipment

| ID | File | Subject |
|---|---|---|
| EQ-01 | equipment/EQ-01_reflow_oven.md | Reflow ovens RF-01 to RF-03 |
| EQ-02 | equipment/EQ-02_smt_line.md | SMT lines SMT-L1 to SMT-L3 |
| EQ-03 | equipment/EQ-03_burn_in_room.md | Burn-in rooms BI-01, BI-02 |
| EQ-04 | equipment/EQ-04_wave_solder.md | Wave solder WS-01 |
| EQ-05 | equipment/EQ-05_test_bank.md | ICT/FCT test bank TEST-01 |
| EQ-06 | equipment/EQ-06_injection_molder.md | Injection molders IM-01 to IM-04 |
| EQ-07 | equipment/EQ-07_chiller.md | Chillers CH-01, CH-02 |
| EQ-08 | equipment/EQ-08_cooling_tower.md | Cooling tower and pumps CT-01 |
| EQ-09 | equipment/EQ-09_air_compressor_fixed.md | Fixed-speed compressors AC-01, AC-02 |
| EQ-10 | equipment/EQ-10_air_compressor_vsd.md | VSD trim compressor AC-03 |
| EQ-11 | equipment/EQ-11_air_dryer.md | Refrigerated air dryer DR-01 |
| EQ-12 | equipment/EQ-12_server_room.md | Server room DC-01 |
| EQ-13 | equipment/EQ-13_ev_charging.md | EV charging bank EV-01 |

### sop

| ID | File | Subject |
|---|---|---|
| SOP-01 | sop/SOP-01_monday_startup.md | Staggered start-up after a weekend or holiday |
| SOP-02 | sop/SOP-02_weekend_shutdown.md | Weekend shutdown checklist |
| SOP-03 | sop/SOP-03_demand_exceedance_response.md | Response to demand WARNING and ALARM |
| SOP-04 | sop/SOP-04_compressed_air_leak.md | Compressed air leak inspection |
| SOP-05 | sop/SOP-05_power_factor_check.md | Capacitor bank and power factor check |
| SOP-06 | sop/SOP-06_heat_wave_precooling.md | Heat wave pre-cooling |
| SOP-07 | sop/SOP-07_meter_data_quality.md | Meter data quality checks |
