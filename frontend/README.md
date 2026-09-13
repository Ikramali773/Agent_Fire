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
- **Claiming a project on sign-in** — a conversation started while signed out belongs to no one, so
  signing in mid-conversation now attaches it to the new account (`POST /case-files/{id}/claim`,
  fired from `App.tsx`). Without it a project started before logging in stayed anonymous forever -
  invisible in Project History and the chat rail, even to the person who had just created it in
  that same browser. Only an *unowned* case file can be claimed, so this is never a way to take
  over someone else's project.
- **Accounts** (`src/auth/`, Phase 2) — `AuthContext.tsx` holds the signed-in `User` (or `null` for
  an anonymous session) and persists the session token to `localStorage`; `LoginModal.tsx` is a
  combined sign-in/sign-up dialog. Entirely optional from the rest of the app's perspective:
  `api/client.ts`'s `setAuthToken(null)` is the default, so every Phase 1 flow (create a case file,
  no login at all) keeps working exactly as before. The top header's account menu is where you sign
  in/out.
- **Conversation history** — the chat transcript is persisted server-side per case file, not held
  in React state, so changing section (or reopening a project from Project History, or reloading
  the browser) restores the conversation instead of losing it. `OverviewPage` reloads it from
  `GET /case-files/{id}/messages` whenever the active project changes, and
  `conversation.ts::toConversationEntries` rebuilds the document-result and classification cards
  from the stored message kind rather than flattening them to text.
  - **A project is created lazily**, on the first real input - a typed answer or an uploaded
    document - not when the Overview page opens. Until then the greeting comes from
    `GET /case-files/opening-message`, which persists nothing. This fixes visiting Overview
    repeatedly filling Project History with empty projects. "New chat" (sidebar) or "New project"
    (Project History header) is how you deliberately start another one; `App.tsx` remembers the
    active project id in `localStorage` so a reload resumes where you left off.
  - **Agent replies render as Markdown** (`design-system/components/Markdown.tsx`) - the model
    answers with GFM tables, headings and bold labels, which previously showed on screen as literal
    pipe characters and asterisks. One renderer is shared by the chat and the report preview so
    both look the same. Raw HTML is deliberately NOT parsed: replies are LLM output shaped by user
    input and uploaded documents, so react-markdown's default of escaping every tag is kept, which
    is safe by construction with no sanitiser to get wrong. The one tag replies actually need is
    `<br>` (the only way to break a line inside a table cell), handled by a ~15-line local remark
    plugin that rewrites just that tag into a real hard break - `rehype-raw` + `rehype-sanitize`
    were measured at +175 kB raw / +54 kB gzipped for the same thing and dropped.
- **Chat history rail** (`src/shell/RecentChats.tsx`) — the sidebar section people expect from
  Claude/ChatGPT: "New chat", then your recent conversations newest-first, one click away from
  being continued (it opens Overview, not the Case File view - picking a project up again almost
  always means continuing the chat). Rows are labelled by project name, falling back to city/state
  then occupancy while the project is still unnamed, since a rail of identical "Untitled project"
  rows is useless. Hover (or keyboard-focus) a row for its delete action.
- **Projects state** (`src/projects/ProjectsContext.tsx`) — one owner of "the signed-in account's
  projects", shared by the chat rail and the Project History page so a delete in either updates
  both immediately instead of leaving a ghost row until reload. `DeleteProjectDialog.tsx` is the
  confirmation: deleting is irreversible and takes the whole conversation with it, so it is a real
  dialog (not `window.confirm`, which can't say what else goes with it, nor show a failed request).
  Deleting the *active* project clears the workspace back to a blank draft; deleting any other one
  leaves what you are working on alone.
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

- **Project History is a project list, not a field-level change log** — `pages/history/ProjectHistoryPage.tsx`
  lists every case file the signed-in account owns (via `GET /users/me/case-files`), lets you open
  one back into its conversation (see "Conversation history" above) and delete it. It does NOT
  track *what* changed and *when* within a single case file (no per-field diff/timeline) - that's a
  real gap if "history" is taken to mean a change log rather than a project list.
- **Chat titles are the project's name, not a summary of the conversation** - unlike Claude/ChatGPT,
  nothing generates a title from what was said; the rail shows whatever identifying facts the case
  file already holds. A chat started and abandoned before any of those are known still reads
  "Untitled project".
- **No search or grouping in the chat rail** - it shows the 8 most recent projects and links to the
  full Project History table beyond that. No "Today/Yesterday/Last 7 days" date grouping, no
  filtering, no rename, no pinning.
- Multi-state NOC checklists, real DWG/BIM plan understanding (Phase 4/5) — see `../backend/README.md`.
