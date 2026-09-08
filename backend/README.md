# Fire Safety AI Agent — Backend (Phase 1)

Implements the parts of the product scope's Phase 1 (`Fire_Safety_AI_Agent_Full_Scope_v3.md`,
Part B):

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
- **LLM abstraction layer** (`app/llm/`) — the only code allowed to call an LLM, per the product
  scope's Part G Principle 1 ("LLM reasons and explains; deterministic engines decide") and its
  B.10 call for a "provider-agnostic abstraction layer." `app/llm/client.py` never talks to a
  specific SDK — it only talks to the `LLMBackend` Protocol (`app/llm/backends/base.py`); each
  provider is one small file implementing `generate_json`/`generate_text`. Two backends exist today:
  - **Groq** (`app/llm/backends/groq_backend.py`) — the **default provider**, since a paid Anthropic
    key wasn't wanted for development. Free tier, OpenAI-compatible API. Default models:
    `llama-3.1-8b-instant` (routine) / `llama-3.3-70b-versatile` (reasoning). Get a free key at
    console.groq.com/keys and set `GROQ_API_KEY`.
  - **Anthropic** (`app/llm/backends/anthropic_backend.py`) — still fully supported; switch to it
    with `FIRE_AGENT_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` set, no code changes needed.
    Default models: `claude-haiku-4-5` / `claude-sonnet-5`.

  Model choice per provider is a cost/quality tradeoff I made, not the user — override with
  `FIRE_AGENT_ROUTINE_MODEL` / `FIRE_AGENT_REASONING_MODEL` if a different model is worth it.
  Groq's open models are less reliable than Claude at strictly following a requested JSON shape, so
  `extract_fields()` validates every field against its expected type and quietly drops (never
  guesses) anything that doesn't fit — a bad field never discards the rest of a good extraction.
  Every LLM-calling method takes an injectable backend so nothing needs a real API key to test (see
  `tests/test_llm_client.py`).
- **Dialogue Manager** (`app/dialogue/`, §B.3/§B.5) — drives the guided intake as a state machine:
  asks each unfilled Case File field in order (skip logic via `field_sources` presence), routes to
  a Knowledge Q&A side-branch and back when the user asks their own question mid-intake, shows a
  confirmation summary once everything's collected (re-extracting against every field so a
  correction like "actually it's 15 floors" is caught), then calls the classifier and returns the
  report. Fails open to the deterministic spine (treats messages as plain answers) when no LLM is
  configured, rather than crashing — verified live with no LLM credentials set.
- **Lightweight Q&A grounding** (`app/knowledge/context.py`) — a short, hand-built summary from the
  already-digitized rule data. **This is NOT the RAG system §B.8 describes** (chunked corpus,
  embeddings, metadata-filtered retrieval) — it's a stand-in that answers a handful of facts
  correctly and honestly says "I don't have that" for everything else, which is the safe behavior
  until real retrieval exists. See that file's docstring before extending it.
- **Document ingest / OCR pipeline** (`app/ingest/`, §B.7) — a tiered, fail-safe pipeline for
  turning an uploaded plan, NOC letter, or certificate (PDF/PNG/JPEG) into text and then into Case
  File fields, escalating tier by tier only when the cheaper tier isn't good enough: Tier 1 native
  PDF text layer → Tier 2 standard Tesseract OCR (with orientation auto-correction) → Tier 3 OCR on
  a preprocessed (upscaled/denoised/binarized) image → Tier 4 vision-LLM page reading → Tier 5 is
  the human-review flag the API response carries when nothing else worked. See
  `app/ingest/README.md` for the tier-by-tier detail. Extracted text is then run through the same
  `LLMClient.extract_fields` machinery used by the chat flow (`app/ingest/fact_extraction.py`), so
  a document-sourced fact is tagged `source: "document"` with confidence scaled by the OCR tier's
  own confidence — a shaky Tier 3 scrape is visibly less trusted than a clean Tier 1 read, per the
  product scope's warning that a plan's extracted text is not geometry-verified and must not be
  treated as more trustworthy just because it came from a plan. Verified against real PDFs (both
  native-text and rasterized "scanned-looking" ones) run through real Tesseract — no mocked OCR in
  the test suite for Tiers 1–3. Reachable via `POST /case-files/{id}/documents` (multipart upload).
- **API** (`app/api/`, `app/main.py`) — CRUD + classify + report, `/start` and `/message` for
  the conversational flow, and `/documents` for document upload.
- **Database persistence** (`app/db/`, §B.10) — `app/store.py` (the only seam every caller uses)
  is now backed by SQLAlchemy instead of an in-memory dict; its public functions
  (`save`/`get`/`delete_all`) are unchanged, so nothing above the store had to change. One Case File
  = one row, stored as a JSON blob keyed by `session_id` (see `app/db/models.py`'s docstring for why
  this isn't a normalized relational schema yet — no query pattern needs it). `DATABASE_URL`
  defaults to a local SQLite file for zero-setup dev; point it at Postgres
  (`postgresql+psycopg://...`) for a real deployment, per §B.10. **Verified against a real local
  Postgres instance**, not just SQLite — round-tripped a full Case File including its nested
  classification result, and independently confirmed the row via `psql` — before this was
  considered done; the automated test suite still runs on SQLite (`tests/conftest.py` pins
  `DATABASE_URL` to a throwaway file) so `pytest` never needs a real database server available.

## Not yet built

- The Node 0 document-upload conversational branch and Node 2a's renewal-upload flow — the OCR
  pipeline (`app/ingest/`) exists, has its own API endpoint, and the frontend has an upload widget
  (a persistent "📎 Upload a plan, NOC letter, or certificate" attach button next to the chat input)
  that the user can use at any point in the conversation; because it writes into the same
  `field_sources` map the dialogue manager's skip logic reads, a field an upload fills in *is*
  skipped in subsequent intake questions and shows up in the confirmation step like any other
  answer. What's still missing is the dialogue manager *offering* the upload as a step (e.g.
  "want to upload your plan instead of answering by hand?") rather than the user having to know the
  attach button exists.
- The residential early-exit shortcut (Node 3a) and per-component Mixed Use breakdown (Node 3b).
- Real RAG knowledge base over the NBCS/NBC corpus (§B.8) — see the Q&A grounding caveat above.
- Mixed Use (Group K) classification — `classify()` currently routes Mixed Use straight to human
  review rather than implementing the per-zone union-of-clauses logic (§B.6.3), since that needs the
  Case File's `occupancy_breakdown` to be wired through the engine.
- State NOC checklists (Gujarat, Maharashtra) — `applicable_state_checklist_id` is always `None` for
  now.
- Voice I/O (§B.1 item 1).

## Running it

```bash
pip install -r requirements.txt      # needs system Tesseract too: apt-get install tesseract-ocr
python -m pytest -q          # 66 tests; real OCR/PDF-generation and DB round-trips, none need network
export DATABASE_URL=postgresql+psycopg://user:pass@localhost/fire_agent  # optional - defaults to local SQLite
export GROQ_API_KEY=gsk_...  # free key from console.groq.com/keys - required for /start, /message, and
                              # document field extraction (OCR text extraction itself needs no LLM key)
python -m uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```

Without `GROQ_API_KEY` (or `ANTHROPIC_API_KEY` if you've switched providers) set,
`/case-files/{id}/classify` + `/report` (the deterministic engine) still work fully; `/message`
degrades to "Sorry, I didn't catch that" for every turn instead of extracting fields from free text;
and `POST /documents` still runs the OCR pipeline and stores the extracted text, but skips turning
it into Case File fields (`fact_extraction_skipped_reason` in the response explains why) — none of
this crashes, but none of it is a full experience without a key.
