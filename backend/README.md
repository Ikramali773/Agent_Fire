# Fire Safety AI Agent — Backend (Phases 1–4)

Implements the parts of the product scope's Phase 1 (`Fire_Safety_AI_Agent_Full_Scope_v3.md`,
Part B):

- **Case File** data contract (`app/models/case_file.py`, §B.4) — plus additions beyond the original
  spec: `occupancy_subdivision`, needed because Table 7A/7C/7E/7F's bands genuinely differ by
  subdivision (e.g. A-I lodging house vs A-V starred hotel) and the original B.4 schema had no field
  for it; `OccupancyBreakdownItem.floor_area_sqm`/`.subdivision`, needed for the same reason on a
  per-component basis once Mixed Use classification (below) actually looks up each component's own
  Table 7 band instead of only tracking which occupancies are present; `floor_wise_area`
  (`FloorAreaItem`), a per-floor area breakdown extracted from a drawing's area-statement table
  (below); and `kitchen_count`/`door_count`, simple counts (not a full schedule with sizes or fire
  ratings) — all three report-facing/informational only, since no digitized NBCS clause currently
  keys off any of them.
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
  - **State NOC checklist framework, §B.10 — deferred/optional** — `app/engine/state_checklists.py`
    attaches `ClassificationResult.applicable_state_checklist_id` for Gujarat/Maharashtra, and the
    content itself is a placeholder (every item a literal `"TODO: ..."`) — see
    `data/rules/state_checklists/README.md` for why: nobody has yet supplied the actual government
    checklist documents, and inventing content that looks official for a compliance product would be
    actively harmful. **This was deliberately deprioritized** (product decision): the product's launch
    plan is India-wide NBCS 2026 Part F classification first, state-specific checklists later only if
    they turn out to be needed. The wiring is left in place (harmless when unused - it only adds a
    placeholder-tagged section to the report) so real content can drop in later without code changes,
    but it is not being actively developed right now.
- **Session security** (`app/auth/`, Phase 4 hardening) — three holes that only matter once somebody
  other than the developer uses this, all flagged in the Phase 1–3 audit and now closed.
  - **Logout revokes the token** (`POST /auth/logout`, `app/auth/revoked_tokens.py`). Tokens are
    stateless HMAC payloads, which is what makes them cheap to verify and also what made logging out
    purely cosmetic: the frontend forgot the token while it stayed valid for the rest of its
    seven-day life, so anyone who had captured it still had the account. Each token now carries its
    own id, so signing out on one device leaves other sessions alone; revoked rows are pruned once
    the token would have expired anyway. Measured at 0.22 ms per authenticated request against 2,000
    revoked rows - a primary-key lookup.
  - **`/auth/login` is rate-limited** (`app/auth/rate_limit.py`, 5 attempts/minute per client+email).
    Without one, passwords could be tried as fast as the network allowed - and since bcrypt is
    expensive *by design*, an unlimited endpoint costs the server more than the attacker, making it
    a denial-of-service lever as much as a brute-force hole. Keyed on client **and** account so an
    attacker cannot lock a victim out of their own account; a correct password clears the counter.
    A **sliding** window, not a fixed one - a fixed window can be walked around by timing requests
    to its edge, which quietly doubles the real allowance for anyone who bothers.
    - **The counters are shared** (`DatabaseBackend`). They used to live in one worker's memory, so
      they reset on restart and behind N workers the effective limit was N× - and N is something an
      attacker raises just by opening more connections, which makes it not really a limit at all.
      They now live in the database this product already requires, so nothing new has to be
      operated, and every worker and instance pointed at it counts the same attempts.
      `tests/test_rate_limit_shared.py` proves that by spending attempts in a genuinely separate
      **process** and asserting the first one still refuses; those tests fail against the in-memory
      backend, which is what makes them worth having.
    - **Cost**: measured at **2.8 ms** per check, and still 2.8 ms with 20,000 attempts live in the
      window. Login does a bcrypt hash anyway (272 ms on this machine), so the limiter is ~1% of
      work the endpoint was already doing. The table holds at most one window of attempts - every
      check deletes what has aged out, across all keys - so it is a counter, not a log, and does not
      grow. The one-off cost of clearing a large backlog (20,000 stale rows) was 44 ms, paid by a
      single request.
    - **It fails open.** A database error is logged and the attempt is allowed. Both endpoints
      behind this limiter need the database to do their real job, so a database that cannot serve
      the limiter cannot serve the login either - failing closed would turn a limiter problem into
      an outage while protecting nothing.
    - The backend is swappable (`set_backend`), which is the seam a Redis or edge-level limiter
      drops into without the endpoints changing. `InMemoryBackend` is kept for tests and deliberate
      single-process use.
  - **The session cut-off is compared at full precision** (`app/auth/tokens.py`). `iat` was whole
    seconds while `sessions_valid_from` is a real instant, so a change at t=100.7 stamped a cut-off
    of 100.7 while the login a fraction later still minted `iat=100` - and 100 < 100.7, so the
    brand-new token was rejected. Since the frontend re-logs in the moment a password changes, this
    locked people out of the account they had just secured, at random, depending on where in the
    second the change landed. It passed one full test run and failed the next, which is exactly what
    a race looks like. `iat` now carries sub-second precision; `decode_token` still accepts the
    integer form so tokens minted before the fix stay valid for the rest of their TTL rather than
    signing everyone out on deploy. Covered by deterministic tests rather than a timing loop.
  - **Account recovery** (`app/api/auth.py`, `app/auth/password_resets.py`, `app/auth/delivery.py`).
    Until this existed a forgotten password meant a lost account, and a *stolen* one could not be
    taken back. Three endpoints: `POST /auth/password` (change, requires the current one — a session
    token alone must not be enough to lock the real owner out), `POST /auth/password-reset/request`,
    `POST /auth/password-reset/confirm` (1-hour, single-use, stored hashed like an invite).
    - **Changing or resetting a password closes every session on the account**, via a
      `sessions_valid_from` cut-off checked on each authenticated request. Revoking only the current
      token would be useless in the case that matters most: someone changing their password
      *because* it may have been stolen gains nothing if the thief's session stays alive.
    - **The reset link is never returned in the HTTP response.** It goes to a pluggable delivery
      backend. Returning it would mean anyone could take over any account just by typing its
      address.
    - **`/auth/password-reset/request` always answers 204**, account or no account. Answering
      differently would turn it into a way to ask "does this person use the product?", and for a
      compliance tool the client list is itself worth protecting. Rate-limited on the same counter
      shape as login so it cannot be used to flood an inbox or to fish for addresses.
    - **Honest limitation**: the default delivery backend (`LoggingDelivery`) writes the link to the
      server log. So today, **password reset only works for someone who can read that log** — which
      is fine for development and is *not* a working recovery flow for real users. A real deployment
      must set a mail backend via `app.auth.delivery.set_delivery()`; `FIRE_AGENT_APP_URL` controls
      the link's origin (default `http://localhost:5173`).
  - **Migrations** (`migrations/`, `app/db/init_db.py`). The schema used to be
    created by `Base.metadata.create_all()` plus an additive add-missing-columns pass that ran on
    every boot. That is fine for adding a nullable column and nothing else: it cannot rename, drop,
    change a type, or backfill, and it leaves no record of what the schema has been. Alembic now
    owns the schema.
    - **Adopting an existing database is the hard part**, and it is not hypothetical — every
      database created before this commit, including the developer's own `case_files.db`, has our
      tables and no `alembic_version`. Running `upgrade head` against one of those would try to
      `CREATE TABLE` over live data. So there are three paths: an empty database gets `upgrade
      head`; one already under Alembic gets whatever is new; one that predates Alembic is
      **reconciled and stamped** once, then is an ordinary versioned database forever.
    - **A bug this caught, by being run rather than reasoned about**: the first version of the
      adoption path stamped a legacy database at the baseline while leaving seven tables missing —
      the stamp asserting a schema that was not there, so the first query against
      `conversation_messages` would fail with the version table insisting everything was fine.
      Covered now by `tests/test_db_migration.py`, which builds a genuine pre-Alembic database with
      raw `sqlite3` and then asserts the *application* works against it, not merely that the tables
      exist.
    - **A third bug, exposed by the very first migration written after the baseline** — which is
      the best argument for having added migrations at all. Adoption built today's whole schema with
      `create_all` and then stamped the database at the *baseline*. That is a contradiction: the
      database held tables from today's models while its version claimed to be at the baseline, so
      the next migration ran against a table that already existed (`table rate_limit_attempts
      already exists`). Had it not failed loudly it would have been worse — a later migration
      silently skipped. A legacy database now walks the ordinary upgrade path through every revision
      in order, with the baseline creating only the tables that are genuinely absent, which is also
      what will make a future *data* migration apply to it.
    - **A second bug, found by an unrelated failing test**: Alembic's `fileConfig()` disables every
      logger not named in the ini it reads, and `alembic.ini` names none of ours — so migrating
      in-process at startup silently switched off `uvicorn.error`, taking the SECURITY warning below
      and uvicorn's request log with it. `env.py` now configures logging only when the CLI is
      driving.
    - `tests/test_db_migration.py` also guards against **drift**: `alembic check` fails the suite if
      `app/db/models.py` changes without a migration, which is the quiet way migrations stop
      describing reality. Verified against a real local Postgres as well as SQLite — all three
      adoption paths, and the drift check.
    - **Honest limitation**: migrations run on startup by default, which keeps a fresh checkout and
      the test suite zero-setup but means N workers booting together would race to apply the same
      revision. `FIRE_AGENT_AUTO_MIGRATE=0` turns that off so a deployment can run
      `alembic upgrade head` as a deploy step, which is what it should do.
  - **The development signing key cannot reach production.** `FIRE_AGENT_AUTH_SECRET` still defaults
    to a string that ships in this repository - anyone who knows it can mint a token for any
    account - so startup now **refuses** when `FIRE_AGENT_ENV` is production/prod/staging, and logs
    a prominent SECURITY warning everywhere else.
- **Compliance engine** (`app/engine/requirements.py`, `GET /case-files/{id}/findings`, Phase 4) —
  Phase 1's classifier determines WHICH requirements apply to a building; nothing ever determined
  whether the building MEETS them, which is why every clause on the Compliance page rendered an
  undifferentiated "unknown" from the day it was built. This compares each installation the matched
  Table 7 band marks `R` against the building's `existing_fire_systems`.
  - The classifier always computed that required set and then **flattened it into a sentence**;
    `ClassificationResult.required_installations` keeps it structured, which is the whole unlock.
    For Mixed Use it is the union across components (clause 3.1.11.2's most-restrictive rule).
  - **"Nothing declared" is UNKNOWN, never NOT MET.** Reporting a building as failing because
    nobody told us what it has would be a false verdict on a compliance record: "you are missing a
    wet riser" and "we do not know whether you have one" are a defect and a question, and the
    product must not confuse them.
  - `existing_fire_systems` is free text, so declarations are matched against a **deliberately
    conservative** synonym list. Anything unmatched is reported as unrecognized, never guessed at -
    a wrong match would mark a requirement met that is not, which is the most damaging mistake this
    module could make. An unrecognized system is surfaced rather than dropped, because it is not the
    same as a system the building does not have.
  - **Negation is understood.** "no sprinklers", "sprinklers: none", "to be provided" and friends
    were originally matched as a DECLARED sprinkler system, crediting a building for the exact thing
    its owner had just said it lacks. A negated clause is now recorded as *declared absent* - which
    is stronger information than silence, so it reads as NOT MET with "explicitly recorded as not
    present" rather than being thrown away.
  - **An entry naming several systems credits all of them.** "fire extinguishers, hose reel, wet
    riser" originally credited only the first and failed the other two - a false failure, which on a
    compliance record is as damaging as a false pass. Entries are split into clauses, which also
    scopes negation ("wet riser installed, no sprinklers" says one of each). Splitting on "and" is
    conditional: two of the eight installations have "and" in their own names, so an unconditional
    split would cut one in half and quote back half a name as the evidence.
  - **"Declared", never "verified".** The system knows an installation was reported; it does not
    know that it exists, covers the right areas, or is correctly designed. Every finding's wording,
    the report section and the UI all keep that distinction rather than letting "met" read as
    "compliant".
  - Derived on read, never stored: it is a pure function of the case file, so there is nothing to
    invalidate when a fact changes.
- **Report generator** (`app/reports/generator.py`, §B.9) — templated Markdown; no LLM call.
- **Report exporters** (`app/reports/exporters.py`, Phase 2) — real PDF (`GET
  /case-files/{id}/report.pdf`) and DOCX (`GET /case-files/{id}/report.docx`) downloads, both
  rendered from the exact same markdown `/report` already returns (never a second source of truth
  for report content). PDF uses PyMuPDF's `Story`/`DocumentWriter` (already a dependency for the
  OCR pipeline — no new heavy/system dependency); DOCX uses a small HTML walker over `python-docx`,
  since the report's markdown is a fixed, simple subset (headings, paragraphs, a flat bullet list,
  bold/italic) with no tables/images/nested lists to handle. The filename in each response's
  `Content-Disposition` is derived from the project name via `safe_report_filename()`, stripped to
  header/path-safe characters. `main.py`'s CORS config explicitly exposes `Content-Disposition` —
  without that, a cross-origin frontend (a different port, the common case in dev) can't read it
  and silently falls back to a generic filename.
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
  - **Rate limiting** — Groq's free/on-demand tier enforces a small per-minute *output*-token quota
    per model (hit live: 1000 tokens/minute), and `generate_json`/`generate_json_from_image` request
    a much smaller `max_tokens` (512, was a flat 1024 for every call — including `generate_text`,
    which keeps the larger budget since prose answers genuinely need more room) to avoid tripping it
    on a single call. A rate limit (or any other transient provider failure — a 5xx, a timeout) that
    still occurs is caught in `LLMClient._call()` and raised as `LLMUnavailableError`, which
    subclasses `LLMNotConfiguredError` so every existing fail-open call site handles it with no
    changes, but the user sees "temporarily rate-limited, try again shortly" rather than a
    misleading "no API key configured" — or, before this, an uncaught 500.
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
  - **Node 3c, per-component subdivision follow-up** — after Node 3b, if a component's occupancy
    needs a subdivision (per `SUBDIVISION_OPTIONS`, e.g. Mercantile's general-shop-vs-underground-
    complex split) but Node 3b's free-text answer didn't say which, a dedicated follow-up question
    is asked for that specific component (dynamically chosen, so it isn't a fixed `dialogue/nodes.py`
    Node) rather than relying on the LLM to infer it from the original answer.
  - **Node 2a, the upload nudge** — answering the goal question prepends a message pointing at the
    upload widget (below) for that one turn, tailored to the goal (renewal gets "upload your existing
    NOC certificate", others get a more general "upload your plan to speed this up") — broadened from
    renewal-only, since the upload speeds up every goal and a user with a plan handy shouldn't have
    to guess that uploading is even an option.
- **Q&A retrieval** (`app/knowledge/`, §B.8) — `app/knowledge/corpus.py` chunks the entire digitized
  rule corpus (`data/rules/**/*.json` + READMEs) into ~500 small, citeable passages;
  `app/knowledge/retriever.py`'s `Retriever` Protocol (mirrors the `LLMBackend` pattern) has two
  implementations:
  - **`KeywordRetriever`** (BM25, hand-rolled, no dependency, no network call) — the **default**,
    since this dev sandbox's network policy blocks every embeddings-capable provider and Hugging
    Face (verified directly: `api.groq.com`, `api.openai.com`, `api.cohere.ai`, `api.voyageai.com`,
    and `huggingface.co` are all unreachable here).
  - **`EmbeddingRetriever`** (`app/knowledge/embedding_retriever.py`) — real semantic (dense-vector)
    search via a local, free `sentence-transformers` model (no per-call cost, no rate limit, same
    "avoid paid APIs" direction as Groq). Opt in with `FIRE_AGENT_RETRIEVER=embeddings` in an
    environment that can actually reach Hugging Face to download the model (~90 MB, first use only);
    falls back to `KeywordRetriever` automatically (never crashes Q&A) if the package isn't
    installed or the model can't load. **Not installed by default** — `pip install
    sentence-transformers` separately if you want it, since it pulls in `torch` and most deployments
    won't need it. **Not verified end-to-end in this dev sandbox** for the same Hugging Face reason
    above — the retrieval/ranking math (cosine similarity, top-k) is fully tested with an injectable
    fake encoder (`tests/test_knowledge_embedding_retriever.py`), and the real encoder is confirmed
    to fail with a clear, catchable error rather than crash when the package is missing (exactly
    this environment's actual state) — but loading and running the real model needs verification in
    an environment with real internet access.

  `app/knowledge/context.py`'s `build_qa_context()` combines whichever retriever is active with the
  original small hand-built summary (kept for the handful of facts a wrong retrieval would be
  costliest to get wrong) and hands both to `answer_question()`. It also optionally takes the
  current `CaseFile` and folds in `build_case_file_context()` — a compact "known facts about this
  case" block covering every field the case file already has a value for (each tagged with its
  recorded source), plus `floor_wise_area`/`kitchen_count`/`door_count`/uploaded document names and
  the classification result if present. This fixes a bug caught in live browser testing: without
  it, a question like "what's the area of the file I just uploaded" was answered as if nothing had
  ever been uploaded, because the Q&A side-branch only ever saw the static code-book summary above -
  never the case file's own already-extracted facts. All three `_safe_answer_question()` call sites
  in `app/dialogue/manager.py` (mid-intake digression, the subdivision follow-up's digression, and
  post-classification open Q&A) now pass the case file through.
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
    architectural drawing. Only covers native-text PDFs' vector tables — Tiers 2/3's OCR path has a
    separate, weaker fix instead (below), since a rasterized/scanned page has no vector ruling lines
    to detect in the first place.
  - **Tiers 2/3 sparse-text supplementary OCR pass** — confirmed directly (not assumed): Tesseract's
    default full-page layout analysis can return *nothing at all* for a ruled-line/bordered table
    image (misclassifies the bordered region as non-text), not just a poor read. A supplementary
    `--psm 11` ("sparse text") pass recovers at least partial content in that case, merged in and
    tagged distinctly so it's clear this is a lower-confidence, best-effort recovery — not real
    row/column reconstruction the way Tier 1's `find_tables()` is for native-text PDFs.
  - `DOCUMENT_FIELD_TYPES` (`app/ingest/fact_extraction.py`) also includes `occupancy_subdivision`
    now — a document implying "a 5-star hotel" or "underground shopping complex" fills the same
    field the chat intake's dedicated subdivision question does, so that question is correctly
    skipped afterward too, not just occupancy_type. An invalid/mismatched code is safe either way:
    the classifier's Table 7 lookup only accepts a subdivision that actually exists for that
    occupancy, routing to human review otherwise.
- **API** (`app/api/`, `app/main.py`) — CRUD + classify + report, `/start` and `/message` for
  the conversational flow, and `/documents` for document upload.
  - **`POST /{id}/what-if`** (Phase 2) — "what if this field were X": merges the given updates into
    a copy of the case file (same merge-and-revalidate `PUT /{id}` uses) and reclassifies it with
    the real `classify()`, but never calls `store_save()` - the real, persisted case file is
    completely unaffected by exploring a scenario. Returns a full hypothetical `CaseFile` so the
    frontend can render it with the same components as the real one.
- **Conversation transcript** (`app/models/conversation.py`, `app/message_store.py`, Phase 2) — the
  chat history, persisted per case file and read back via `GET /case-files/{id}/messages`
  (oldest-first, `limit` + `before_id` cursor). `/start`, `/message` and `/documents` each record
  what was said; a document result and the moment of classification are stored as *structured*
  messages (kind + payload) rather than prose, so a reloaded transcript re-renders the same cards
  the user saw live instead of flattening to text. Fixes a reported problem: the transcript used to
  live only in frontend state, so changing section lost the whole conversation with no way back.
  - **Why its own table, not a list on the Case File**: a transcript is append-only and unbounded.
    Inside the Case File's JSON blob, every message would rewrite the entire history and then ship
    all of it on every case file response - quadratic in a long project. One indexed row per
    message keeps an append O(1) and lets a long conversation be paged instead of loaded whole.
- **Optimistic locking on the Case File** (`app/store.py`, `CaseFileRecord.version`) — every write
  path is a read-modify-write, and without this two requests each read, each mutated, each saved,
  **both got a 200, and one person's edit vanished with nothing anywhere saying so**. Reproduced,
  not theoretical: two browser tabs, or a document upload finishing while the user saves a field.
  `store.save(case_file, expected_version=...)` is now a compare-and-set, and every endpoint that
  reads then writes passes the version it read; the API answers **409** instead of swallowing the
  loss.
  - **The check is part of the UPDATE statement**, not a read followed by a write: two requests can
    both pass a Python-side version check before either commits, and then both write. That is not
    hypothetical either - the first version of this fix did exactly that, and the concurrency test
    caught it. A conditional `UPDATE ... WHERE version = :expected` is atomic in every database;
    whoever gets `rowcount == 1` won.
  - Omitting the version keeps the old last-write-wins behavior, so a script or an older client is
    not broken. A row written before the column existed reads as version 1.
- **Paged project list** (`GET /users/me/case-files?limit=&offset=`) — this returned an account's
  entire history in one response, **measured at 0.81 MB of JSON for 500 projects and unbounded**,
  to render eight rows in the chat rail. Now a page (50 by default, 200 max) plus the `total`, so
  the UI can say what it is not showing. `/users/me/chat-titles` takes the same window, so it cannot
  quietly become the unbounded query the project list just stopped being.
- **`CaseFileRecord.requires_review`** — denormalized out of the JSON blob for the same reason
  `owner_user_id` is. The review queue used to load every owned case file **plus one lookup per
  grant**, then discard the ones that were not flagged: O(all your projects) to answer a question
  about a handful. Now one indexed query covering owned and shared-with-me together — measured at
  500 projects, it loads **10 rows instead of 500**. `store.save()` is the only writer, so it cannot
  drift from the blob, and `init_db._backfill_requires_review` fills it in for rows written before
  it existed (a NULL here is a flagged case that has become invisible, which is exactly what the
  review queue exists to prevent).
- **Password length is validated** (`app/auth/security.py`) — bcrypt 5 *raises* on a password over
  72 bytes rather than truncating it as older releases did, so an unvalidated passphrase from a
  password manager **crashed signup with a 500** (reproduced). Now a clear 422. Deliberately not
  truncated: hashing the first 72 bytes silently would make the rest of someone's passphrase
  decorative, and two different long passwords would open the same account. It is a *byte* limit,
  not a character one — an emoji is four bytes.
- **Human review** (`app/models/review.py`, `app/review_store.py`, `app/grant_store.py`, Phase 3) —
  the classifier has always been able to say "a person has to look at this", in 15 different
  situations, and that flag was a dead end. Phase 3 closes the loop.
  - **Typed reasons** — `ReviewReasonCode` + `ClassificationResult.review_reasons`, so a queue can
    say "3 cases blocked on a not-permitted combination" instead of making a reviewer read 15
    paragraphs of notes. All 15 sites go through one `_flag_review()` helper that sets the flag,
    records the typed reason and appends the prose *together*, so they cannot drift.
    - **Two real bugs this surfaced.** Writing the invariant test for it (the flag is true exactly
      when there is a reason) found two paths out of `_classify_single_occupancy` that returned
      before the flag could be set. A small Institutional or Hazardous building — one below Part F's
      applicability threshold — came back with **no review flag at all**, because the
      mandatory-occupancy check sat after the "does not apply" early return; a hospital the engine
      declined to classify looked like a clean automated answer. And an undecidable applicability
      check appended its note and returned unflagged, while the identical failure one step later
      (the Table 7 lookup) did flag — the same blocker reaching the user two different ways
      depending on which line it hit. Both fixed, both covered by regression tests.
  - **Verdicts** — `GET`/`POST /case-files/{id}/review`, backed by an append-only
    `case_file_reviews` table. The current status is *derived* ("latest event, or `needs_review`"),
    never stored, so a case that was approved, reopened when a fact changed, and approved again is
    distinguishable from one approved once — and a newly flagged case needs no write at all to
    appear in a queue. `needs_review` is rejected as a verdict (422): it is the derived start
    state, and accepting it would let a review be silently rewound.
    - **A verdict NEVER rewrites the classification.** This is the architecture of the feature, not
      an implementation detail: Part G Principle 1 is "LLM reasons and explains; deterministic
      engines decide", and letting a person hand-edit the engine's verdict breaks it exactly as
      surely as letting the LLM do it. A reviewer who believes the output is wrong changes the
      FACTS, and the engine reclassifies from those.
  - **Sharing** (`POST`/`GET`/`DELETE /case-files/{id}/shares`) — `_check_access` grew capability
    levels (`Access.READ` / `WRITE` / `OWN`), because with reviewers the question is no longer "do
    you have access" but "access to do what". A reviewer reads, downloads and records verdicts; they
    cannot edit a field, continue the conversation, reclassify, delete, or re-share onward. A
    verdict on facts the reviewer could have edited is worth nothing. Sharing by address needs the
    recipient to have an account already; for everyone else there are **invites** (below).
    Anonymous Phase 1 case files are completely unchanged (no owner means open to whoever holds the
    session id), and that is covered by its own tests.
  - **Invites** (`app/invite_store.py`, `app/api/invites.py`, `POST`/`GET`/`DELETE
    /case-files/{id}/invites`, `GET`/`POST /invites/{token}[/accept]`) — sharing by address only
    reaches someone who has already signed up, which is *not* the consultant you need the first time
    you ask them to look at something. An invite is a 14-day, single-use, revocable link.
    - **The link goes to the OWNER, once, not to an inbox.** They are already authorised to share
      this project, so handing it to them is secure without a mail transport, and spares the product
      one more thing to operate. It is returned only on the response that creates it: the token is
      stored **hashed**, so a link that is not copied then cannot be recovered, only revoked and a
      new one issued. Listing invites later shows who was invited and whether they accepted, never
      the link.
    - **Accepting requires an account** — a compliance verdict has to be attributable to a person,
      and "whoever had the link" is not one. The preview (`GET /invites/{token}`) is deliberately
      unauthenticated and deliberately thin (project name, who sent it, expiry — nothing about the
      building): the recipient has no account yet, and being asked to create one without being told
      what for is how an invitation gets ignored; but whoever holds the link has not accepted yet
      and may not be the person it was meant for.
    - Accepting with a **different** address than the invitation was sent to is allowed — a
      consultant may well sign up with another one, and refusing would strand a legitimate reviewer
      over a typo. Both addresses stay on the record.
    - Accepting creates an ordinary reviewer grant, so every access rule above applies unchanged:
      an invite is a way to *reach* a reviewer, never a second, weaker kind of access.
  - **Queue** (`GET /users/me/review-queue`) — every flagged case this account is responsible for,
    its own plus ones shared with it, **oldest first**. Unlike every other list in this product: a
    chat rail is newest-first because you are resuming what you were just doing; a compliance queue
    is oldest-first because the case waiting longest is the one most at risk of being forgotten.
    Approved and rejected cases drop out by default (`include_settled=true` to see them).
- **Organisations** (`app/models/organisation.py`, `app/organisation_store.py`,
  `app/assignment_store.py`, `app/api/organisations.py`, Phase 4) — sharing was one project to one
  person at a time. Six colleagues and forty projects is two hundred and forty shares; the day
  somebody leaves, you have to remember all of them. An organisation is a named group of accounts:
  a project shared with it is readable by every member, and a member who leaves loses that access
  in one step.
  - **A team grants READ, never WRITE.** Members read, download the handoff pack, record a verdict
    and can be assigned a review — exactly the reviewer capability that already existed, because
    the reason for it has not changed: *a verdict on facts the reviewer could have edited is worth
    nothing*, and that does not stop being true because the reviewer is a colleague.
  - **Only a project's OWNER can put it into a team.** Being able to administer a team must never
    become a way to pull in a colleague's other work — the same rule as "a reviewer cannot re-share
    onward", applied to groups. Removing it again is allowed to the owner or an admin; neither
    deletes anything.
  - **Deleting a team deletes no projects.** An organisation is a way of sharing work, never where
    it lives. Only its creator can dissolve it; an admin added later manages the team but not its
    existence. The creator also cannot be demoted or removed — an organisation whose last admin
    demoted themselves is one nobody can add a member to or delete, and there is no support desk
    here to unstick it.
  - **A non-member gets a 404, not a 403**, for anything addressed by organisation id. Whether an
    organisation exists is itself something only its members should be able to find out.
  - `organisation_case_files` is a **link table**, not a column on `case_files`: which group can see
    a project is a relationship between two things, not a fact about the building — and the Case
    File model is untouched by this whole feature.
- **Review assignment and due dates** (`app/assignment_store.py`,
  `GET`/`POST /case-files/{id}/assignment`, `GET .../assignment/history`, Phase 4) — who is expected
  to look at a flagged case, and by when.
  - **Append-only**, like `case_file_reviews`: a case reassigned twice reads differently from one
    assigned once, and an UPDATE in place could not tell you which you were looking at.
    *Unassigning writes a row with no assignee* rather than deleting one — a deliberate act,
    recorded as such, and distinguishable from never having been assigned.
  - **Assignment is never a back door to access.** You can only assign a case to someone who could
    already open it; otherwise "assign to anyone" would quietly become "share with anyone",
    bypassing both the owner-only share rule and the team it goes through. Covered by a test that
    also asserts the would-be assignee still gets a 403.
  - Who may assign: the project's owner, or an **admin** of a team it is shared with. A plain member
    cannot — being able to read a case is not the same as being able to hand it to a colleague.
  - **Due dates are advisory and the product says so, in the API description and on screen.**
    Nothing enforces one or acts when it passes; the queue marks the case overdue and that is the
    whole of it. A settled case is never overdue — it is done, not late, and saying otherwise would
    leave permanent red rows nobody can clear.
  - The queue carries each row's assignment, fetched in **one query for the whole page**
    (`current_for_sessions`), not one per row — the O(n) round trips the queue was rewritten to
    avoid in the first place.
- **Per-user preferences** (`app/models/preferences.py`, `app/preferences_store.py`,
  `GET`/`PUT /users/me/preferences`, Phase 4) — a pinned chat is per-USER state, and the Case File
  schema is fixed: there is no field on it for "this person pinned this project", and inventing one
  would put one account's preference on a record that gets shared with reviewers. So pins lived in
  the browser and did not follow the account to a second device. This is where they live now.
  - **Typed, not an open JSON bag.** A free-form key-value store would let the frontend write
    anything, which is how a preferences table becomes an unversioned second schema nobody can
    reason about. Adding a preference is a deliberate act with a migration behind it.
  - **Whole-object replace, not a patch.** The object is small and always edited as a whole, and a
    patch endpoint would need a way to say "set this list to empty" distinct from "leave this list
    alone" — exactly the ambiguity that makes patch APIs error-prone for collections. The response
    is what was actually *stored* (duplicates dropped, list capped), not what was sent, so a caller
    echoing its own request back cannot drift out of step.
  - **A pin is not access.** Ids only; the projects themselves still go through every ordinary
    access check, so pinning a session id you do not own grants nothing. Covered by a test.
  - Deleting a project unpins it for every account, through the same cascade that clears its
    messages, changes, reviews, grants and invites — otherwise a pin outlives what it points at and
    the list fills with ids that resolve to nothing.
  - What is deliberately NOT here: the active project and the session token. Those are per-BROWSER
    — "which project was I last looking at" should differ between the laptop and the phone, and
    syncing it would make two open tabs fight.
- **Consultant handoff pack** (`app/reports/handoff.py`, `GET /case-files/{id}/handoff[.pdf|.docx]`,
  Phase 3) — the report plus the three things only this system knows: **why** review is required
  (the engine's typed reasons), **where every fact came from** (`field_sources`, which has been
  recorded since Phase 1 and which no export had ever surfaced), and **what has changed and when**
  (the Phase 2 change log). The report states conclusions; the question a professional putting their
  name to a sign-off actually asks is "where did each of these numbers come from, and what changed
  since?". Invents nothing — like `generator.py`, it only restates what is already recorded. The
  DOCX walker learned real tables for it, and `render_pdf`/`render_docx` now take markdown so the
  report and the pack share one renderer instead of growing two subtly different ones. A change
  history longer than the export cap **says how many entries it is showing** - a compliance document
  that quietly drops history is worse than one that admits the limit.
  - **A third gap this exposed**: a field typed into the Case File page (`PUT /case-files/{id}`)
    recorded **no provenance at all**. The dialogue path and the ingest path had always recorded it;
    this one never did, so a user-confirmed fact reached the pack with no source. `PUT` now records
    each edited field as user-confirmed, with the coerced value rather than the raw request body.
- **`GET /users/me/chat-titles`** (Phase 2) — one title per chat, taken from its first *user*
  message (the agent's greeting is identical in every conversation and would title them all the
  same), collapsed to one line and trimmed at a word boundary. What lets the sidebar tell projects
  apart before one is named. Deliberately NOT a Case File field: a title is a presentation detail
  of the conversation, the Case File schema is fixed, and persisting one would mean keeping it in
  step with a transcript that already contains the answer. Scoped to case files the account owns,
  so it can never surface another account's conversation; one grouped query rather than loading
  every message of every project.
- **Case File change log** (`app/models/change_log.py`, `app/change_log.py`, Phase 2) — the per-field
  audit trail, read back via `GET /case-files/{id}/changes` (newest-first, `limit` + `before_id`
  cursor). Every endpoint that mutates a case file records what changed and where it came from:
  `PUT` as `user`, a conversational turn as `dialogue`, a document upload as `document`, a stage
  transition as `system`, each with the acting account when there is one. This is what Project
  History (a project *list* showing current state only) could never answer: "this building was 24 m
  yesterday and 68 m today - who changed it, and off the back of what?".
  - **Scope, deliberately**: it logs Case File FACTS. The classification result is not duplicated
    here - every classification is already stored in the transcript as a structured
    `classification_result` message with its full payload, and a second copy would be one more
    thing to keep in step. The `conversation_stage` transition to "classified" IS logged, so the
    timeline still shows when it happened. `field_sources` is excluded too: it changes alongside
    nearly every field, so logging it would double the timeline's length to repeat what each
    entry's own `source` already says.
  - **Why its own table**: the same reason the transcript has one - a change log is append-only and
    unbounded, `record` is one INSERT per changed field, and old rows are never rewritten.
  - A `what-if` never appears in it (it reclassifies a hypothetical copy and is never persisted),
    and a no-op `PUT` writes nothing rather than padding the timeline.
- **UTC on every timestamp** — `CaseFile.created_at`/`updated_at` used `datetime.utcnow()` (naive)
  and SQLite's `DateTime(timezone=True)` drops `tzinfo` on read, so the API emitted
  `"2026-09-13T07:13:16"` with no offset. A browser parses an ISO string with no offset as *local*
  time, which meant a change made seconds ago read as hours ago for every user outside UTC. The
  model default is now timezone-aware and `app/timestamps.py::as_utc` re-labels anything read back
  from the database - including Case File rows written before the fix, whose blobs still hold a
  naive timestamp. (The frontend also treats an offset-less timestamp as UTC, so an existing
  database displays correctly without a migration.)
- **`POST /case-files/{id}/claim`** (Phase 2) — attaches an anonymous case file to the calling
  account. The one operation that may set `owner_user_id` after creation, closing a real gap: a
  project started before signing in used to stay anonymous forever, invisible in Project History
  even to the person who had just created it. Only an UNOWNED case file can be claimed - claiming
  one you already own is a no-op (idempotent, so a retry or a double-invoked frontend effect is
  harmless), and claiming someone else's is the same 403 as any other access, so this can never
  become a way to take over a project by guessing a session id.
- **`DELETE /case-files/{id}`** (Phase 2) — deletes a project: the case file AND its whole
  transcript, its change log, its review history AND every share, in one step. All of it, explicitly - a user deleting a project
  expects their conversation and its history to go with it, not to be left behind in the database. Irreversible (no soft-delete, no undo), so
  the frontend confirms first. Ownership is enforced by the same `_check_access()` as every other
  endpoint, so one account can never delete another's project.
- **`GET /case-files/opening-message`** (Phase 2) — the assistant's greeting for a case file that
  doesn't exist yet, persisting nothing. Fixes the other half of the same report: opening the
  Overview page used to create (and persist) a case file immediately, so every visit - and every
  switch back to that section - added an empty project to Project History. The frontend now creates
  a case file lazily, on the first real input (a typed answer or an uploaded document).
- **Accounts** (`app/auth/`, `app/api/auth.py`, `app/api/users.py`, Phase 2 — "cases belong to a
  person instead of only an anonymous session") — `POST /auth/signup`, `POST /auth/login`,
  `GET /auth/me`, and `GET /users/me/case-files` (Project History's starting point). Deliberately
  additive, not a breaking change: `CaseFile.owner_user_id` (new, optional) is `None` for an
  anonymous case file, which stays exactly as open as all of Phase 1 always had it (the
  `session_id` itself is the access control) - every existing test and the entire pre-Phase-2
  frontend flow keeps working with zero changes. A case file WITH an owner is locked to that
  account; `app/api/case_files.py`'s `_check_access()` is the one place that's enforced, called by
  every endpoint that touches an existing case file.
  - **Passwords**: `bcrypt` directly (`app/auth/security.py`).
  - **Session tokens**: hand-rolled HMAC-signed tokens (`app/auth/tokens.py`), NOT a JWT library -
    this dev sandbox's system-installed `cryptography` package (which every JWT library pulls in,
    even for the plain HMAC algorithm this needs) is broken here (a Rust/cffi panic on import,
    confirmed directly; pip can't cleanly replace it either - "Cannot uninstall cryptography ...
    RECORD file not found", a Debian-packaging quirk). Rather than depend on an environment-specific
    `pip install --ignore-installed` workaround, the token format uses only `hmac`/`hashlib` from
    the standard library - same two-part (payload + signature) shape as a JWT, so swapping to a
    real JWT library later costs nothing if a use case ever needs one of its other features.
    **Set `FIRE_AGENT_AUTH_SECRET` in any real deployment** - the built-in default is
    dev-only and clearly labeled as such.
  - **`owner_user_id` cannot be reassigned via `PUT /case-files/{id}`** - stripped from the update
    dict before it's ever merged, so neither an accidental nor a malicious request body can
    transfer/plant a case file onto a different account after creation.
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
  - **Schema changes against an existing database** — now **Alembic** (`migrations/`,
    `app/db/init_db.py`; see the Phase 4 hardening section above for the full account, including two
    bugs that only showed up when it was run rather than reasoned about). The problem that forced
    this: `create_all` only creates tables that don't exist; it never alters one that does, so a
    column added to a model after a database was created went silently missing and broke every query
    mentioning it — `no such column: case_files.owner_user_id`, hit live against a pre-Phase-2 local
    `case_files.db`. The additive add-missing-columns pass that fixed *that* could never do more:
    no renames, drops, type changes, or NOT-NULL backfills. It survives today only as the one-shot
    step that reconciles a pre-Alembic database before stamping it; everything from here on is a
    real migration.

## Not yet built

- **Plan geometry / the Building Digital Model (the other half of Phase 4)** — reading travel
  distances, exit widths, staircase positions and compartment boundaries out of a drawing needs
  CAD/BIM parsing (DWG/IFC), which is not built and has no sample files here to build against.
  Uploaded drawings are read for their *text and tables* today (see the ingest pipeline above);
  that is not the same as understanding the geometry, and inventing geometry for a fire-safety
  product would be actively harmful. This is what "Plans" in the nav is waiting for.
- **Travel-distance and exit-capacity findings** — Table 4 (travel distance) needs the construction
  type and a measured travel distance, and Table 3 (capacity factors) needs measured stair and exit
  widths. None of those are Case File fields, so evaluating them would mean inventing the inputs.
  Table 3's own digitized data also carries an `extraction_note` warning that several occupancy rows
  were not cleanly separated in OCR and need verification against the source before being trusted.
  Occupant load (Table 2) *is* computable from area and occupancy, but on its own it yields no
  pass/fail without those widths.

- Real state NOC checklist content for Gujarat/Maharashtra — the framework (data model, engine hook,
  report section) is fully wired per the "State NOC checklist framework" section above, but every
  checklist item ships as an explicit placeholder — **deliberately deprioritized**, not scheduled
  for this phase, pending both the actual government source documents and a product decision that
  state-specific checklists are worth building (the current plan is India-wide classification first).
- `EmbeddingRetriever`'s real model verified end-to-end — see the "Q&A retrieval" section above; the
  retrieval math is tested for real, but loading and running the actual `sentence-transformers`
  model needs an environment with real internet access, which this dev sandbox doesn't have.
- Table reconstruction for the OCR path (Tiers 2/3) — Tier 1's `find_tables()` only works on a
  native-text PDF's vector ruling lines; a scanned/photographed drawing's schedule table gets a
  best-effort supplementary sparse-text OCR pass (recovers content the primary pass would otherwise
  miss entirely — see the "Document ingest / OCR pipeline" section above) rather than real
  row/column reconstruction.
- Kitchen presence/door count are simple counts (`kitchen_count`, `door_count`), not a full schedule
  with sizes or fire ratings — informational/report-facing only, same as `floor_wise_area`, since no
  digitized NBCS clause currently keys off either one.
- Voice input only fills the chat's text box (via the browser's SpeechRecognition) rather than
  auto-sending — a deliberate choice (misheard transcripts should be reviewable before sending), not
  a gap, but worth noting if a fully hands-free flow is wanted later.

## Running it

```bash
pip install -r requirements.txt      # needs system Tesseract too: apt-get install tesseract-ocr
alembic upgrade head         # optional: the app does this itself on startup (see migrations/README)
python -m pytest -q          # 578 tests; real OCR/PDF-generation, DB round-trips, and rule-data-backed
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

### Generated API types

`scripts/export_openapi.py` dumps this app's OpenAPI schema (FastAPI already builds it automatically
from the Pydantic models) to `../frontend/openapi.json`, which `frontend`'s `npm run generate:types`
turns into `frontend/src/api/schema.ts` — see `frontend/README.md`'s "Generated API types" section
for the full workflow. Run `python scripts/export_openapi.py` (from `backend/`) whenever a Case
File/API model changes, then regenerate on the frontend side and commit both files.
