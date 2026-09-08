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
- **Report viewer** (`src/components/ReportView.tsx`) — modal that fetches and renders the
  Markdown compliance report (`react-markdown`) once the case reaches `classified`.
- **API client** (`src/api/client.ts`) — thin fetch wrapper; `types.ts` mirrors the backend's
  `CaseFile` Pydantic model by hand (no generated client yet — a later cleanup, not a blocker).

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

Not yet verified: a real end-to-end chat conversation with an actual Groq/Anthropic key (no key was
available in the environment this was built in) — voice I/O and document upload aren't built on
either side yet, so there's nothing to test there.

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

- Voice input/output toggle (§B.1 lists voice as in-scope for Phase 1; not implemented on either
  the frontend or backend side).
- File upload widget (blocked on the backend's OCR ingest pipeline, §B.7, which doesn't exist yet).
- Auth/accounts, project history — Phase 1 is explicitly single-session only per the product scope.
- A generated API client — `src/types.ts` is hand-maintained against the backend's Pydantic models
  and will drift if one changes without the other; fine for now, worth automating later.
