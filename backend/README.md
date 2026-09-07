# Fire Safety AI Agent — Backend (Phase 1)

Implements the parts of the product scope's Phase 1 (`Fire_Safety_AI_Agent_Full_Scope_v3.md`,
Part B) that don't require an LLM/vendor decision yet:

- **Case File** data contract (`app/models/case_file.py`, §B.4) — plus one addition beyond the
  original spec: `occupancy_subdivision`, needed because Table 7A/7C/7E/7F's bands genuinely differ
  by subdivision (e.g. A-I lodging house vs A-V starred hotel) and the original B.4 schema had no
  field for it.
- **Deterministic classification engine** (`app/engine/`, §B.6) — reads the digitized rule data at
  `../data/rules/nbcs_2026_partf/` and never guesses: applicability, the high-rise flag, and Table 7
  band matching are all driven by structured criteria traceable to a specific clause. Where the
  source table's own phrasing was ambiguous (a compound "height X OR area Y" condition), the
  matched band is tagged `confidence: "interpreted"` and surfaced to the report rather than silently
  trusted — see `data/rules/nbcs_2026_partf/table7/table7a_residential.json`'s
  `band_matching_convention` for the exact rule used.
- **Report generator** (`app/reports/generator.py`, §B.9) — templated Markdown; no LLM call.
- **Minimal API** (`app/api/`, `app/main.py`) — create/update a case file, classify it, get the
  report. This gives the eventual dialogue manager (§B.3, §B.5) a concrete backend to call into.

## Not yet built

- The guided conversational intake / question tree (§B.5) and the LLM-driven Dialogue Manager
  (§B.3) — blocked on an LLM provider decision (see the product scope §B.11 research item 1).
- The fail-safe OCR/PDF ingest pipeline (§B.7).
- The RAG knowledge base over the NBCS/NBC corpus (§B.8).
- Persistent storage — `app/store.py` is an explicitly-labeled in-memory placeholder; swapping it
  for PostgreSQL (per §B.10) is a self-contained infra task.
- Mixed Use (Group K) classification — `classify()` currently routes Mixed Use straight to human
  review rather than implementing the per-zone union-of-clauses logic (§B.6.3), since that needs the
  Case File's `occupancy_breakdown` to be wired through the engine.
- State NOC checklists (Gujarat, Maharashtra) — `applicable_state_checklist_id` is always `None` for
  now.

## Running it

```bash
pip install -r requirements.txt
python -m pytest -q          # 22 tests, all against the real digitized rule data
python -m uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```
