# Fire Safety AI Agent — Frontend (Phase 1)

React + TypeScript chat UI (per product scope §B.10) for the Phase 1 conversational agent. Talks
to the backend at `../backend/` via its `/case-files/*` REST + chat endpoints — see that directory's
README for what's actually implemented server-side.

## What's here

- **Chat window** (`src/components/ChatWindow.tsx`) — message bubbles, input box. Creates a case
  file and starts the guided intake automatically on load.
- **Case summary panel** (`src/components/CaseSummaryPanel.tsx`) — shows every field the agent has
  collected so far, and the classification result once available. Reads directly off the Case
  File's `field_sources` map so it only shows what's actually been confirmed, never a guess.
  Mixed Use's `occupancy_breakdown` and document-extracted `floor_wise_area` (a per-floor area
  breakdown from a drawing's area-statement table) each get their own readable formatting instead of
  the generic array-to-string fallback, which would otherwise print raw `[object Object]` entries.
- **Report viewer** (`src/components/ReportView.tsx`) — modal that fetches and renders the
  Markdown compliance report (`react-markdown`) once the case reaches `classified`.
- **Document upload widget** (`src/components/DocumentUpload.tsx`) — a persistent "📎 Upload a
  plan, NOC letter, or certificate" attach button next to the chat input, available at any point in
  the conversation. Validates the file type client-side (PDF/PNG/JPEG) before sending; the backend
  does the real OCR work (`../backend/app/ingest/README.md`). Posts the upload as `multipart/form-data`
  to `POST /case-files/{id}/documents`, then renders the result as a chat message (which fields were
  found, a low-confidence warning if the OCR tier used wasn't a clean text-layer read, or a plain
  explanation if no LLM was configured to turn the extracted text into fields) and refreshes the
  case summary panel — an uploaded field shows up there and is skipped in the guided intake, same as
  a typed answer.
- **API client** (`src/api/client.ts`) — thin fetch wrapper; `types.ts` mirrors the backend's
  `CaseFile` Pydantic model by hand (no generated client yet — a later cleanup, not a blocker).
- **Voice I/O** (`src/components/VoiceInputButton.tsx`, §B.1) — a 🎤 button next to the chat input
  using the browser's own `SpeechRecognition` API to fill the text box (never auto-sends — a
  misheard transcript should be reviewable before it's submitted, same as typing), and a "🔊 Read
  replies aloud" checkbox above the chat that uses `SpeechSynthesis` to read each new agent message.
  Both are pure feature detection: on a browser without `SpeechRecognition` (Firefox, most of Safari)
  the mic button renders nothing at all rather than a broken control, and the read-aloud checkbox
  only appears where `speechSynthesis` exists. No backend involvement either way.

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

## Not yet built

- The dialogue manager only proactively offers the upload widget when the user says they're
  renewing an existing NOC — for every other goal it's still a standing option the user has to
  notice, not something the agent proposes. See the backend README's "Not yet built" section.
- Auth/accounts, project history — Phase 1 is explicitly single-session only per the product scope.
- A generated API client — `src/types.ts` is hand-maintained against the backend's Pydantic models
  and will drift if one changes without the other; fine for now, worth automating later.
