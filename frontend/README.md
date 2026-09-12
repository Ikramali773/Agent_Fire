# Fire Safety AI Agent — Frontend

React + TypeScript "Fire Safety Compliance Workspace" (the professional application shell that
replaced the original Phase 1 chat prototype - see git history for that redesign) for the
conversational agent + Phase 2 features. Talks to the backend at `../backend/` via its
`/case-files/*`, `/auth/*`, and `/users/*` REST + chat endpoints — see that directory's README for
what's actually implemented server-side.

## What's here

- **Application shell** (`src/shell/`) — the persistent frame every page renders inside: a top
  header (project switcher, breadcrumb, code-edition badge, sync state, account menu), a
  collapsible left sidebar (`Sidebar.tsx`, driven by `nav.ts` - Phase 1's active pages plus every
  future-phase page shown but disabled and labeled "Coming in Phase X"), a collapsible right Case
  Inspector panel (`CaseInspector.tsx` - every known field with its source/confidence), and a
  persistent disclaimer footer.
- **Design system** (`src/design-system/`) — tokens (`tokens.css`: color, spacing, radius,
  elevation, type) plus the reusable components built on them (`StatusPill`, `SourceBadge`,
  `DataRow`, `Card`, `Button`, `ProgressSteps`, `DocumentResultCard`, `Modal`, `Drawer`, ...).
- **Pages** (`src/pages/`) — `overview/` (the AI copilot conversation: typed message cards, staged
  document-processing feedback, classification results), `case-file/` (the full structured
  inspector with click-to-edit, wired to `PUT /case-files/{id}`), `documents/` (drag-and-drop
  upload + history), `compliance/` (status rollup + requirements, plus Phase 2's What-If scenario
  panel), `reports/` (the Markdown report preview + real PDF/DOCX downloads).
- **Accounts** (`src/auth/`, Phase 2) — `AuthContext.tsx` holds the signed-in `User` (or `null` for
  an anonymous session) and persists the session token to `localStorage`; `LoginModal.tsx` is a
  combined sign-in/sign-up dialog. Entirely optional from the rest of the app's perspective:
  `api/client.ts`'s `setAuthToken(null)` is the default, so every Phase 1 flow (create a case file,
  no login at all) keeps working exactly as before. The top header's account menu is where you sign
  in/out.
- **API client** (`src/api/client.ts`) — thin fetch wrapper (auto-attaches the auth token when
  signed in); `types.ts` derives `CaseFile`/`User`/etc. from a *generated* schema (`src/api/schema.ts`)
  instead of a hand-maintained duplicate — see "Generated API types" below.
- **Voice I/O** (`src/components/VoiceInputButton.tsx`, §B.1) — a mic button in the Overview
  composer using the browser's own `SpeechRecognition` API to fill the text box (never auto-sends —
  a misheard transcript should be reviewable before it's submitted, same as typing). Pure feature
  detection: on a browser without `SpeechRecognition` (Firefox, most of Safari) it renders nothing
  at all rather than a broken control.

## Verified

Ran both servers together and drove the UI with a real headless browser (Playwright) rather than
just `npm run build` — this caught three real backend bugs in the LLM fail-open path (fixed, with
regression tests, in the same session) that unit tests alone had missed:
- Multi-turn chat renders correctly and updates the case summary panel live.
- The classify → report flow was exercised end-to-end (backend classifies a Storage building,
  frontend shows the "View full report" button, opens the modal, renders the Markdown correctly —
  headings, bullet lists, bold labels all intact).
- The graceful "no LLM configured" fallback message displays correctly instead of a crash or a
  blank error, on every turn (not just the first).
- The document upload widget was exercised the same way, against a real backend backed by a real
  local Postgres instance: selected a real generated PDF, uploaded it, confirmed the "Reading
  document…" state, confirmed the resulting chat message and no console errors, and independently
  confirmed via `psql` that the upload was persisted onto the Case File's `source_documents`.
- Voice I/O was driven the same way: confirmed the real browser reports `SpeechRecognition` and
  `speechSynthesis` support, clicked the mic button and confirmed it fails gracefully (a visible
  error message, no crash, no console error) rather than actually transcribing — this sandbox's
  headless Chromium has no real microphone/speech-service backend, which is an environment
  limitation, not a code path this app controls. For the read-aloud side, intercepted
  `window.speechSynthesis.speak` and confirmed it's called with the exact agent reply text on every
  new message; the sandbox reports 0 installed TTS voices, so audible playback itself couldn't be
  confirmed here (also an environment limitation — a normal browser has system voices).

Not yet verified: a real end-to-end chat conversation with an actual Groq/Anthropic key (no key was
available in the environment this was built in) — that also means the document upload flow has only
been verified in its no-LLM-configured degraded mode (OCR runs, field extraction is skipped); and a
real microphone/TTS voice, for the reasons above.

## Running it

```bash
npm install
cp .env.example .env.local   # only needed if the backend isn't on localhost:8000
npm run dev                  # http://localhost:5173
```

The backend must be running separately (see `../backend/README.md`) with `FRONTEND_ORIGINS`
including `http://localhost:5173` (that's already the backend's default) and, to actually hold a
conversation rather than see the graceful fallback message on every turn, `GROQ_API_KEY` (or
`ANTHROPIC_API_KEY` + `FIRE_AGENT_LLM_PROVIDER=anthropic`) set.

```bash
npm run build   # type-checks (tsc -b) then produces dist/
npm run lint    # oxlint
```

### Generated API types

`src/api/schema.ts` is generated from the backend's OpenAPI schema, not hand-written - the frontend
and backend's `CaseFile` etc. shapes can no longer silently drift out of sync. `src/types.ts` derives
the types the rest of the app actually imports (`CaseFile`, `ClassificationResult`, ...) from it,
wrapped in `Required<...>` since FastAPI/Pydantic marks any field with a default as "not required" in
the OpenAPI spec (a *request* could omit it) even though a *response* the backend sends always
includes every field (Pydantic serialization never omits one) - so treating them as always-present
is a correct, not just convenient, simplification.

To regenerate after a backend model change:
```bash
cd ../backend && python scripts/export_openapi.py   # writes ../frontend/openapi.json
cd ../frontend && npm run generate:types             # writes src/api/schema.ts
```
Commit both `openapi.json` and `schema.ts`. Verified: built the real backend's OpenAPI schema this
way and confirmed `npm run build`/`npm run lint` are clean against the generated types, plus a live
browser check that a real API response still renders correctly end-to-end.

## Not yet built

- A real Project History page (Phase 2) — the backend's `GET /users/me/case-files` exists and is
  tested, but nothing in the frontend calls it yet; "Project History" is still a "Coming in Phase 2"
  sidebar placeholder.
- Multi-state NOC checklists, real DWG/BIM plan understanding (Phase 4/5) — see `../backend/README.md`.
