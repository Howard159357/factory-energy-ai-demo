# Security tests

Prompt-injection and tool-misuse tests for the energy agent. All content is synthetic.

- `injection_corpus/` holds 18 fictional plant documents, each with one planted attack. They look
  like ordinary corpus documents on purpose: same header line, SOP numbers (SOP-21 to SOP-38),
  no hint that they are tests. For a test run they are copied with the real corpus into a
  temporary staging folder under ordinary paths (`docs/knowledge/sop/SOP-21_...`) and indexed
  into a separate test collection, so neither the folder, the file name nor the title gives them
  away. They never enter the knowledge base the agent normally uses.
- `attacks.yaml` describes each attack: the benign question that retrieves the document, the
  technique, and what counts as success (planted markers, a system-prompt leak, a forbidden tool).
  `A01`-`A12` are the design set the guardrails were built against; `H01`-`H06` were written
  afterwards and never used to tune them.
- `test_injection.py` runs every attack with a deliberately gullible scripted model under four
  defence profiles (part of `pytest`).
- `results/` holds the latest `python -m factory_energy eval security` runs.

Method and results: [docs/SECURITY.md](../docs/SECURITY.md).
