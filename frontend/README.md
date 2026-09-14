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
- **Account recovery** (`src/auth/`, `src/entry/`, Phase 4) — `LoginModal` grew a "Forgot your
  password?" mode; `ChangePasswordModal.tsx` hangs off the top header's account menu.
  - The reset confirmation deliberately says *"if there's an account for …"*, never *"we've emailed
    you"*. The backend answers identically whether or not the account exists, precisely so this page
    cannot be used to ask who uses the product — wording that claimed a message was sent would give
    that away again, and a test asserts it does not.
  - Changing a password closes **every** session on the account, this browser's included (the
    backend stamps a cut-off). `AuthContext.changePassword` immediately re-logs in with the new
    password, so the person who actually made the change stays signed in here and only here. Without
    that the very next request would 401 and look like a bug.
  - Confirmations are checked client-side before submitting. A reset link is single-use, so a typo
    in the confirmation would set the password to something nobody knows with no second chance.
- **Links that arrive from outside the app** (`src/entry/`, Phase 4) — `?reset=<token>` and
  `?invite=<token>` on the app's own origin. There is no router here (navigation is `activeView`
  state in `App.tsx`), so rather than adding one for two links, the query string is read **once** at
  startup and the matching full-screen step takes over the whole app until it is done. Each step
  strips the token from the address bar when it finishes: a token is a credential, and leaving it in
  the URL leaves it in the history of a machine that may be shared.
  - `ResetPasswordScreen.tsx` never signs the user in afterwards. `/auth/password-reset/confirm`
    answers 204 and deliberately never says whose account it was, so there is no session to hand
    back — the screen says so and sends them to sign in.
  - `AcceptInviteScreen.tsx` shows **what the invitation is before asking for an account**, from the
    unauthenticated preview endpoint: being told to sign up with no idea what for is how an
    invitation gets closed. It also states the limits of what accepting grants, because a reviewer
    signing an NBCS verdict needs to know what they are looking at. Accepting lands them on
    **Review** — what they were invited for — not Overview, whose conversation they cannot continue.
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
  Claude/ChatGPT: "New chat", a search box, pinned chats, then recent conversations grouped by when
  they were last touched (Today / Yesterday / Previous 7 days / Previous 30 days / Older), each one
  click away from being continued. It opens Overview, not the Case File view - picking a project up
  again almost always means continuing the chat.
  - **Titles** come from the project's name, falling back to what the user opened the conversation
    with (`GET /users/me/chat-titles`), then the location, then the occupancy. "A twelve storey
    hospital in Pune" identifies a project far better than its city does, and a rail of identical
    "Untitled project" rows is useless.
  - **Grouping** counts calendar days, not elapsed hours (`shell/chatGroups.ts`): something touched
    at 11pm is "Yesterday" by 1am, not "Today".
  - **Search** filters across every project the account has, not just the ~8 the rail shows -
    otherwise it could only ever find what was already on screen.
  - **Row menu** (`shell/ChatRowMenu.tsx`) — pin, rename, delete behind one overflow button, since
    three inline controls do not fit a narrow rail. Renaming sets the Case File's own
    `project_name`, so it shows up in that project's change log like any other edit rather than
    being separate hidden UI state.
  - **Pins** (`projects/usePinnedChats.ts`) live on the ACCOUNT, via the per-user preferences
    store (`/users/me/preferences`), so they follow the person to another browser or a phone. They
    used to live in `localStorage`, which meant they did not — that was documented as a limitation
    rather than hidden, and this removes it.
    - Signed out there is no account to attach a pin to, so it stays in this browser, namespaced by
      account id so two people sharing a machine don't see each other's.
    - **Pins made before signing up are merged in, once.** Someone who pinned ten projects and then
      created an account should not silently lose them. The local copy is cleared only after the
      merge succeeds, so a failed request cannot destroy the only copy there is.
    - Writes are **optimistic**: the pin flips immediately and the request follows. Pinning is a UI
      convenience, and making someone watch a round trip to see a star fill in would be worse than
      reconciling a rare failed write on the next load.
    - A slow response for the previous account cannot overwrite the new one's pins — a real hazard
      when signing out and back in as someone else on a shared machine, and covered by a test.
- **Team** (`src/pages/team/`, Phase 4) — the Team nav item is live: your teams, their members, and
  which of your projects each can see. A project shared with a team is readable by every member, and
  removing someone takes away all of it at once rather than one project at a time.
  - The page states what a team does NOT grant, for the same reason `SharePanel` does: members read,
    download the handoff pack and record a verdict, and cannot edit a fact, continue the
    conversation, delete a project or share it onward.
  - "Share this project with the team" appears only for a project you **own** — administering a team
    is not a way to pull in a colleague's work, and the page says that rather than showing a button
    that 403s.
  - It says plainly that a colleague needs an account already, and points at the per-project invite
    link for someone who hasn't signed up. That is the one thing people get wrong about teams here,
    and there is no mail transport to fix it with.
- **Assignment and due dates** (`src/pages/review/AssignmentPanel.tsx`, and the queue, Phase 4) —
  who owes a review, and by when.
  - The panel **never claims a due date is enforced**: "a note to the people involved… nothing here
    enforces it or acts when it passes". A compliance tool that implied otherwise would be making a
    promise it does not keep, and a test asserts the wording.
  - A date-only deadline is sent as **midday UTC**, not midnight — read back in a timezone behind
    UTC, midnight would land on the previous day. Also tested, because it is the kind of thing that
    looks right until someone in a different timezone opens it.
  - The queue marks an overdue case with a plain `Overdue` pill, never as a compliance status (this
    product does not issue one), and offers an "only cases assigned to me" filter — shown only when
    something actually is, since a filter that can only empty the list is noise. Filtering is
    client-side because the rows are already there.
  - The panel distinguishes "nobody has been asked yet" from "explicitly unassigned", because the
    backend records those differently and collapsing them would lose the distinction it keeps.
- **Projects state** (`src/projects/ProjectsContext.tsx`) — one owner of "the signed-in account's
  projects", shared by the chat rail and the Project History page so a delete in either updates
  both immediately instead of leaving a ghost row until reload. `DeleteProjectDialog.tsx` is the
  confirmation: deleting is irreversible and takes the whole conversation with it, so it is a real
  dialog (not `window.confirm`, which can't say what else goes with it, nor show a failed request).
  Deleting the *active* project clears the workspace back to a blank draft; deleting any other one
  leaves what you are working on alone.
- **Findings** (`src/pages/findings/`, Phase 4) — the Findings nav item is live: each installation
  the matched Table 7 band requires, with its verdict, the sentence explaining that verdict, and the
  recorded text it was matched to (so a wrong match can be challenged rather than trusted).
  - **A declared system is rendered `info`, never `pass`** (`lib/findings.ts`), and the page says
    "Declared, not verified" outright. The product knows an installation was reported; it does not
    know it exists, covers the right areas, or is correctly designed. A green pass would assert
    compliance the footer on every page disclaims — asserted in a test so it cannot drift.
  - "Not known" and "not declared" are visually and verbally distinct, because a question and a
    defect must not look the same.
  - The same verdicts replace the Compliance page's blanket per-clause "unknown".
- **Review** (`src/pages/review/`, Phase 3) — the Review nav item is live. Master-detail rather than
  a table, because acting on a case needs the reasons, the handoff pack and the verdict form
  together; bouncing between a list page and a detail page per case is how a queue stops getting
  worked.
  - `ReviewQueue.tsx` renders the backend's order verbatim (**oldest first** — see the backend
    README for why) and never re-sorts. Each row says whether the case is yours or shared with you,
    because that decides whether you can change its facts at all.
  - `ReviewDetail.tsx` shows the engine's typed reasons in plain words *and* in full, the handoff
    pack download, the verdict form, and the whole verdict history. It says out loud that a verdict
    is recorded alongside the classification and never replaces it.
  - `ReviewBanner.tsx` surfaces the flag on **Compliance and Case File**, where people already look
    at the classification — Review is a page nobody visits unless something sends them there, and a
    flagged case that never gets reviewed is the failure this whole phase exists to prevent. It says
    *why*, from the typed reasons, rather than a bare "needs review" that reads as boilerplate.
  - `SharePanel.tsx` (owner only) spells out exactly what a reviewer can and cannot do, rather than
    leaving the owner to guess what they just granted. It offers two ways in, because the person you
    need to review something usually doesn't have an account yet: **Add** by address (works only for
    an existing account) and **Invite by link** (works for anyone). When Add fails with the 404 that
    means "no account for that address", the panel turns that dead end into a one-click
    `Create invite link` — before invites existed it said *"they need to sign up first"*, which left
    the owner stuck on precisely the reviewer they needed. The fresh link is shown **once**, and the
    panel says so: the token is stored hashed server-side, so a link not copied then is gone for
    good. Pending invites are listed separately from live reviewers, and an accepted invite is
    filtered out of that list — it is already a grant, and showing both would read as two reviewers
    where there is one.
  - **Signed out, the Review page still reviews the open project.** There is no queue without an
    account (a queue spans projects; an anonymous session has one), but the backend treats an
    anonymous case file as open to whoever holds its session id, verdicts included — so sending
    someone here from the banner and then showing them a sign-in wall would be a dead end of our own
    making. Sharing is hidden there, since there is no account to share as.
- **Signing out actually signs you out** — `logout()` revokes the token server-side before this
  browser forgets it. Fire-and-forget on purpose: if that request fails the token lives until it
  expires, but this browser still ends up signed out — leaving someone *appearing* logged in because
  the network blipped is worse. A rate-limited sign-in (429) gets its own readable message rather
  than the raw status line.
- **Edit conflicts are surfaced, never swallowed** — a case file carries a `version`, and every save
  sends it back. If someone else changed the project in between, the server answers 409 and the page
  says *"Someone else changed this project while you had it open. Reload…"* rather than silently
  overwriting them. **Never retried automatically**: an automatic retry would reintroduce exactly
  the overwrite the version check exists to prevent.
- **The project list is paged** (`ProjectsContext`) — it used to fetch an account's entire history
  (0.81 MB of JSON at 500 projects, unbounded) to render eight rail rows. Now a page at a time, with
  `total` and `hasMore`, and a "Show more (50 of 60)" button on Project History so a paged list is
  honest about the rest rather than implying it is everything.
- **Read-only projects** (`lib/access.ts`) — `canEditCaseFile` mirrors the backend's `Access.WRITE`
  so the UI never offers an action the server will refuse. On a project shared with you for review,
  the Overview composer is disabled and says why, and the Case File page's edit pencils are not
  rendered at all. A mirror, not the enforcement — the server decides; this stops the UI inviting
  someone into a 403.
- **Case File history** (`pages/case-file/ActivityTimeline.tsx`) — the "History" card at the bottom
  of the Case File page: every field that changed, what it changed from and to, where the change
  came from (a direct edit, the conversation, a document, the system) and when. Fields set together
  in one edit are folded into a single event rather than repeating the same timestamp down the
  page, and it pages backwards with a cursor rather than loading a long project's whole history.
  This is the per-field change log Project History never was - that page lists projects and shows
  each one's *current* state.
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
npm test        # vitest run - 177 tests
```

### Tests

`npm test` (vitest + Testing Library, jsdom). The suite deliberately targets the logic that has
actually broken here before, rather than chasing coverage:

- `lib/caseFileFields.test.ts` — `normalizeClassification`'s defaults (`Required<>` is *shallow*,
  which shipped a build failure once), and `formatValue` rendering a legitimate `false`/`0` instead
  of treating it as missing.
- `pages/overview/conversation.test.ts` — a restored transcript rebuilds document and classification
  *cards* from the stored message kind, keyed by message id, rather than flattening to text.
- `design-system/components/Markdown.test.tsx` — GFM tables render, `<br>` works inside a table
  cell, and **raw HTML is escaped**. That last group is a load-bearing security property, not a
  nicety: this content is LLM output shaped by user input and uploaded documents, so anything that
  starts parsing raw HTML has to break those tests first.
- `projects/ProjectsContext.test.tsx` — ordering, waiting for auth before fetching, and a failed
  delete leaving the project listed instead of vanishing optimistically.
- `projects/DeleteProjectDialog.test.tsx` — nothing is deleted until the destructive button is
  pressed, a failure keeps the dialog open, and it can't be double-submitted.
- `lib/changeLog.test.ts` + `pages/case-file/ActivityTimeline.test.tsx` — history entries read as
  prose (an absent value is "Not set", a list of structured rows is "3 entries" rather than raw
  JSON), fields set together fold into one event, and paging asks for changes before the oldest one
  already held.
- `shell/RecentChats.test.tsx` + `shell/chatGroups.test.ts` + `projects/usePinnedChats.test.ts` —
  titles fall back in the right order, grouping counts calendar days rather than elapsed hours,
  search reaches projects the rail isn't showing, a pinned chat is lifted out of the date groups,
  two accounts sharing a browser don't see each other's pins, a pin made before signing up is
  merged into the account exactly once, and a slow response for the previous account cannot
  overwrite the new one's.
- `pages/review/*.test.tsx` + `lib/review.test.ts` + `lib/access.test.ts` — the review vocabulary
  (notably that "approved" is **not** rendered as a compliance pass: this product does not certify
  anything, and the footer on every page says so), the banner staying invisible unless the engine
  actually flagged the case, sharing being hidden from anyone who cannot share, the verdict form
  never offering the derived `needs_review`, and a reviewer being unable to edit a project they can
  only read.
- `auth/LoginModal.test.tsx` + `auth/ChangePasswordModal.test.tsx` + `entry/*.test.tsx` — the reset
  confirmation never claiming the address has an account, a mistyped confirmation being caught
  before a single-use link is spent, the backend's own "invalid, already used, or expired" reaching
  the user (the difference between "try again" and "ask for a new link"), an invite preview refusing
  to accept without an account, and an expired or already-used invitation not offering an Accept
  button at all.
- `pages/review/AssignmentPanel.test.tsx` + the assignment cases in `pages/review/ReviewQueue.test.tsx`
  — a refused assignment explaining *why* (the person cannot see the project) rather than just that
  it failed, a due date going out as an instant rather than a bare date, the panel offering no
  controls to someone who cannot assign, "never assigned" reading differently from "explicitly
  unassigned", and the queue's mine-only filter staying hidden until something is actually mine.
- `lib/relativeTime.test.ts` — unit selection, and that an offset-less API timestamp is read as UTC
  rather than as local time (see the backend README's "UTC on every timestamp"): without that, a
  change made seconds ago showed as hours ago for anyone outside UTC.

Test files live beside the code in `src/`, so `tsc -b` type-checks them along with everything else —
vitest alone does not, and that difference caught four real type errors in the fixtures the runner
had been happy with. No `globals: true`: `describe`/`it`/`expect` are imported explicitly, which
keeps `tsconfig.app.json`'s `types` list untouched.

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

- **A chat's title is its first message, not a summary of the conversation** - unlike Claude/ChatGPT,
  no model writes a title from what was discussed; the rail shows the opening message verbatim,
  trimmed. A chat abandoned before anything was typed still reads "Untitled project".
- **Chat search matches the title only** - not the conversation's contents or the case file's
  fields, and it is a plain substring match with no ranking. Finding "that project where we
  discussed the atrium" still means opening chats.
- **Nothing is emailed, ever** — there is no mail transport in this product. An invite link and a
  password-reset link both have to reach their recipient some other way (the owner copies the invite
  link; a reset link goes to the server log until a real backend is configured), and nobody is told
  when a case is assigned to them or falls overdue. They have to come and look. This is now the
  single biggest gap: several shipped features work but depend on someone being told out of band.
- **Nothing escalates** — a case can be assigned with a due date and the queue marks it overdue, but
  no reminder goes anywhere and no case moves on its own. Deliberate for now (see the Assignment
  section: the product does not pretend to enforce a deadline it cannot act on), but a firm running
  a real queue will want escalation.
- **A team's projects are listed by id, not by name** — the Team page can say how many projects a
  team holds and let the owner add or remove the open one, but it cannot list them, because the
  endpoint returns session ids only. Naming them needs a projects-for-this-team query that respects
  each caller's access.
- **"Approved" is one person's sign-off, not a compliance verdict** — deliberately. The product
  does not certify anything (see the footer on every page). Phase 4's compliance engine now gives
  per-requirement verdicts (see Findings above), and those are separate from a reviewer's approval:
  the engine says what the code requires and what has been declared, the reviewer says whether they
  are satisfied.
- **Plans is still a placeholder, and says why.** Geometry-aware plan viewing needs CAD/BIM parsing
  that isn't built; uploaded drawings are read for their text and tables today, which is not the
  same thing. The nav entry stays, honestly labelled, rather than being faked.
- **Findings cover firefighting installations only** — travel distance and exit capacity need
  measured inputs the Case File doesn't hold. See `../backend/README.md`.
- Multi-state NOC checklists — see `../backend/README.md`.
