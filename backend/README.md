# Fire Safety AI Agent — Backend (Phase 1)

Implements the parts of the product scope's Phase 1 (`Fire_Safety_AI_Agent_Full_Scope_v3.md`,
Part B):

- **Case File** data contract (`app/models/case_file.py`, §B.4) — plus additions beyond the original
  spec: `occupancy_subdivision`, needed because Table 7A/7C/7E/7F's bands genuinely differ by
  subdivision (e.g. A-I lodging house vs A-V starred hotel) and the original B.4 schema had no field
  for it; `OccupancyBreakdownItem.floor_area_sqm`/`.subdivision`, needed for the same reason on a
  per-component basis once Mixed Use classification (below) actually looks up each component's own
  Table 7 band instead of only tracking which occupancies are present; and `floor_wise_area`
  (`FloorAreaItem`), a per-floor area breakdown extracted from a drawing's area-statement table
  (below) — report-facing/informational only, since no digitized NBCS clause currently keys off it.
- **Deterministic classification engine** (`app/engine/`, §B.6) — reads the digitized rule data at
  `../data/rules/nbcs_2026_partf/` and never guesses: applicability, the high-rise flag, and Table 7
  band matching are all driven by structured criteria traceable to a specific clause. Where the
  source table's own phrasing was ambiguous (a compound "height X OR area Y" condition), the
  matched band is tagged `confidence: "interpreted"` and surfaced to the report rather than silently
  trusted — see `data/rules/nbcs_2026_partf/table7/table7a_residential.json`'s
  `band_matching_convention` for the exact rule used.
  - **Mixed Use (Group K), §B.6.3** — `classify_mixed_use()` runs the normal per-occupancy Table 7
    lookup for every component in `case_file.occupancy_breakdown` (each against the shared building
    height but its own floor area), unions the required installations across all of them (clause
    3.1.11.2's "most restrictive provisions" rule), and adds the pairwise fire-separation rating
    between every two occupancies present from
    `data/rules/nbcs_2026_partf/group_k_mixed_occupancy_separation.json` — a combination the matrix
    marks `"NP"` (not permitted) is always forced to human review rather than silently accepted.
  - **State NOC checklist framework, §B.10** — `app/engine/state_checklists.py` attaches
    `ClassificationResult.applicable_state_checklist_id` for Gujarat/Maharashtra. **The checklist
    content itself is a placeholder** (every item a literal `"TODO: ..."`) — see
    `data/rules/state_checklists/README.md` for why: nobody has yet supplied the actual government
    checklist documents, and inventing content that looks official for a compliance product would be
    actively harmful. This is the wiring (data model → engine → report section) that real content
    drops into later without further code changes.
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
  - **Node 3a, the residential early-exit shortcut** — once a Residential building's height/area
    fall within Table 7A's own self-certification threshold (read from the digitized rule data, not
    a hardcoded copy of it), the egress/existing-systems questions are skipped entirely (they don't
    change a self-certification outcome) and the agent says why before jumping to confirmation.
  - **Node 3b, Mixed Use breakdown** — when occupancy is "Mixed Use", an intake node asks for each
    component occupancy + its own floor area (extracted as a nested `list[OccupancyBreakdownItem]`
    in one LLM call — see `app/llm/schema.py`'s new Pydantic-model/Enum schema support, added for
    this), feeding `classify_mixed_use()` above.
  - **Node 2a, the renewal-upload nudge** — answering the goal question with "renew an existing NOC"
    prepends a message pointing at the upload widget (below) for that one turn, rather than only
    supporting upload as a button the user has to notice unprompted.
- **Q&A retrieval** (`app/knowledge/`, a lightweight pass at §B.8) — `app/knowledge/corpus.py` chunks
  the entire digitized rule corpus (`data/rules/**/*.json` + READMEs) into ~500 small, citeable
  passages; `app/knowledge/retriever.py` is a `Retriever` Protocol (mirrors the `LLMBackend` pattern)
  with one implementation today, a hand-rolled BM25 keyword scorer — no external dependency, no
  network call. `app/knowledge/context.py`'s `build_qa_context()` combines this with the original
  small hand-built summary (kept for the handful of facts a wrong retrieval would be costliest to
  get wrong) and hands both to `answer_question()`. **This is deliberately not full embeddings-based
  semantic search** — real §B.8 needs a network path to an embeddings-capable provider (Voyage,
  OpenAI, Cohere, ...), and this dev sandbox's network policy blocks all of them (verified directly:
  `api.groq.com`, `api.openai.com`, `api.cohere.ai`, `api.voyageai.com`, and `huggingface.co` are all
  unreachable here). The `Retriever` Protocol exists so a real embeddings backend can be dropped in
  later, in an environment that can actually reach one, without any caller changing.
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
  - **Table detection** — Tier 1 also runs PyMuPDF's `find_tables()` on every page, so a drawing's
    ruled-line schedule (an area statement, a door schedule) gets handed to the LLM as real rows
    instead of scrambled-together flat text. This is what makes `floor_wise_area` (a per-floor area
    breakdown, distinct from the single `built_up_area_sqm` total) reliably extractable from a real
    architectural drawing. Only covers native-text PDFs' vector tables today — the OCR path (Tiers
    2/3) has no equivalent table reconstruction yet, a known gap for scanned/photographed drawings.
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

- The Node 0 document-upload conversational branch offering itself proactively for *every* goal —
  the OCR pipeline (`app/ingest/`), the frontend upload widget, and Node 2a's renewal-specific nudge
  (above) all exist, but the dialogue manager only proactively suggests uploading when the user says
  they're renewing an existing NOC. For every other goal, uploading is still a standing button the
  user has to notice on their own, not a step the agent offers.
- Real embeddings-based semantic search for Q&A (§B.8) — see the "Q&A retrieval" section above for
  what exists instead (real chunking + keyword/BM25 retrieval) and exactly why full embeddings
  aren't wired up yet (a verified network-access constraint in this dev sandbox, not a design
  choice) — a Retriever Protocol is already in place for it.
- Real state NOC checklist content for Gujarat/Maharashtra — the framework (data model, engine hook,
  report section) is fully wired per the "State NOC checklist framework" section above, but every
  checklist item ships as an explicit placeholder pending the actual government source documents.
- Per-component subdivision disambiguation UI for Mixed Use — `OccupancyBreakdownItem.subdivision`
  exists and `classify_mixed_use()` uses it, but Node 3b's single free-text prompt relies on the LLM
  inferring a subdivision from phrasing (e.g. "a 5-star hotel component") rather than asking a
  dedicated follow-up per component the way the single-occupancy `subdivision` node does.
- Voice input only fills the chat's text box (via the browser's SpeechRecognition) rather than
  auto-sending — a deliberate choice (misheard transcripts should be reviewable before sending), not
  a gap, but worth noting if a fully hands-free flow is wanted later.

## Running it

```bash
pip install -r requirements.txt      # needs system Tesseract too: apt-get install tesseract-ocr
python -m pytest -q          # 113 tests; real OCR/PDF-generation, DB round-trips, and rule-data-backed
                              # classification (including Mixed Use + state checklists), none need network
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
