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
    - **Honest limitation**: in-process and dependency-free, so the counters reset on restart and
      are NOT shared across workers. Behind N workers the effective limit is N×. A large improvement
      on "no limit", and a poor substitute for a shared store (Redis) or a limit at the edge.
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
    verdict on facts the reviewer could have edited is worth nothing. Sharing needs the recipient to
    have an account already — inviting an unknown address would mean sending mail, which this
    product does not do, and silently creating an account for someone is worse than an honest 404.
    Anonymous Phase 1 case files are completely unchanged (no owner means open to whoever holds the
    session id), and that is covered by its own tests.
  - **Queue** (`GET /users/me/review-queue`) — every flagged case this account is responsible for,
    its own plus ones shared with it, **oldest first**. Unlike every other list in this product: a
    chat rail is newest-first because you are resuming what you were just doing; a compliance queue
    is oldest-first because the case waiting longest is the one most at risk of being forgotten.
    Approved and rejected cases drop out by default (`include_settled=true` to see them).
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
  - **Schema changes against an existing database** (`app/db/init_db.py`) — `create_all_tables()`
    only creates tables that don't exist yet (SQLAlchemy's `create_all`); it never alters one that
    already exists, so a column added to a model after a database file/instance was first created
    (e.g. `CaseFileRecord.owner_user_id`, Phase 2) went silently missing from any pre-existing
    database and broke every query mentioning it with `no such column: case_files.owner_user_id` -
    hit live against a pre-Phase-2 local `case_files.db`. Fixed with a lightweight, additive-only
    migration pass that runs right after `create_all` on every boot: it adds any column a model
    declares that the live table is missing. **Not a real migration tool** - no renames, drops, type
    changes, or NOT-NULL backfill; only ever safe for a nullable column with no dependent backfill,
    which is true of everything added this way so far (see `test_db_migration.py`). A schema change
    beyond that needs real migrations (Alembic).

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
python -m pytest -q          # 198 tests; real OCR/PDF-generation, DB round-trips, and rule-data-backed
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
