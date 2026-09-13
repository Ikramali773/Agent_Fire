import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { CaseFile } from "../../types";
import { Composer } from "./Composer";
import { useAuth } from "../../auth/AuthContext";
import { isReadOnlyCaseFile } from "../../lib/access";
import { ConversationMessage } from "./ConversationMessage";
import { nextEntryId, toConversationEntries, type ConversationEntry } from "./conversation";
import { normalizeClassification } from "../../lib/caseFileFields";
import { parseQuickOptions } from "../../lib/quickOptions";
import "./OverviewPage.css";

interface Props {
  caseFile: CaseFile | null;
  onCaseFileChange: (caseFile: CaseFile) => void;
  onBusyChange: (busy: boolean) => void;
}

// The AI compliance workspace - a copilot over the Case File, not the whole
// application.
//
// Two things this page deliberately does NOT do, both fixing real reported
// problems:
//   1. It never creates a case file just because it mounted. Opening this
//      page used to POST /case-files immediately, so every visit (and every
//      section switch back) created a project, filling Project History with
//      empty ones. A case file is now created lazily, on the first real
//      input - a typed answer or an uploaded document - via ensureCaseFile().
//      Until then the greeting comes from /case-files/opening-message, which
//      persists nothing.
//   2. It never treats its local `entries` state as the record. The
//      transcript is persisted server-side and reloaded on mount, so leaving
//      this page (or reopening the project later) no longer loses the chat.
export function OverviewPage({ caseFile, onCaseFileChange, onBusyChange }: Props) {
  const { user } = useAuth();
  const readOnly = isReadOnlyCaseFile(caseFile, user);
  const [entries, setEntries] = useState<ConversationEntry[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Which session's transcript `entries` currently holds. Also set straight
  // after a lazy create, so the load effect below doesn't re-fetch over the
  // optimistic entries of the very turn that created the case file.
  // `undefined` (not null) is the "nothing loaded yet" sentinel - null is a
  // real value here, meaning "a draft with no case file yet".
  const loadedSessionId = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    onBusyChange(busy);
  }, [busy, onBusyChange]);

  const sessionId = caseFile?.session_id ?? null;

  useEffect(() => {
    if (loadedSessionId.current === sessionId) return;
    loadedSessionId.current = sessionId;
    setBusy(true);
    setError(null);

    // Staleness is guarded by re-checking the ref when the request
    // resolves, rather than by an unmount cleanup flag: React StrictMode
    // invokes this effect twice in dev, and cancelling the first run's
    // state updates would leave `busy` stuck true forever (the second run
    // early-returns above, so nothing would ever clear it).
    (async () => {
      try {
        if (sessionId) {
          const messages = await api.getMessages(sessionId);
          if (loadedSessionId.current === sessionId) setEntries(toConversationEntries(messages));
        } else {
          const { agent_message } = await api.getOpeningMessage();
          if (loadedSessionId.current === sessionId) {
            setEntries([{ kind: "agent", id: nextEntryId(), text: agent_message }]);
          }
        }
      } catch (err) {
        if (loadedSessionId.current === sessionId) setError(describeError(err));
      } finally {
        if (loadedSessionId.current === sessionId) setBusy(false);
      }
    })();
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  // Creates the case file on first real input and records the greeting the
  // user has already been shown, so the persisted transcript matches the
  // screen. Returns the case file to act on - callers must use this rather
  // than the `caseFile` prop, which is still null on the turn that creates it.
  const ensureCaseFile = useCallback(async (): Promise<CaseFile> => {
    if (caseFile) return caseFile;
    const created = await api.createCaseFile();
    const started = await api.startConversation(created.session_id);
    loadedSessionId.current = started.case_file.session_id;
    onCaseFileChange(started.case_file);
    return started.case_file;
  }, [caseFile, onCaseFileChange]);

  const handleSend = useCallback(
    async (text: string) => {
      setEntries((prev) => [...prev, { kind: "user", id: nextEntryId(), text }]);
      setBusy(true);
      setError(null);
      try {
        const active = await ensureCaseFile();
        const previousStage = active.conversation_stage;
        const result = await api.sendMessage(active.session_id, text);
        onCaseFileChange(result.case_file);
        setEntries((prev) => [...prev, { kind: "agent", id: nextEntryId(), text: result.agent_message }]);
        if (previousStage !== "classified" && result.case_file.conversation_stage === "classified") {
          setEntries((prev) => [
            ...prev,
            { kind: "classification-result", id: nextEntryId(), result: normalizeClassification(result.case_file.classification_result) },
          ]);
        }
      } catch (err) {
        setError(describeError(err));
      } finally {
        setBusy(false);
      }
    },
    [ensureCaseFile, onCaseFileChange],
  );

  const handleUploadDocument = useCallback(
    async (file: File) => {
      setError(null);
      setBusy(true);
      const entryId = nextEntryId();
      setEntries((prev) => [...prev, { kind: "document-uploading", id: entryId, fileName: file.name }]);
      try {
        const active = await ensureCaseFile();
        const result = await api.uploadDocument(active.session_id, file);
        onCaseFileChange(result.case_file);
        setEntries((prev) =>
          prev.map((entry) =>
            entry.id === entryId ? { kind: "document-result", id: entryId, fileName: file.name, summary: result.summary } : entry,
          ),
        );
      } catch (err) {
        setError(describeError(err));
        setEntries((prev) => prev.filter((entry) => entry.id !== entryId));
      } finally {
        setBusy(false);
      }
    },
    [ensureCaseFile, onCaseFileChange],
  );

  const lastAgentEntry = [...entries].reverse().find((entry) => entry.kind === "agent");
  const quickOptions =
    !busy && lastAgentEntry && lastAgentEntry.kind === "agent" && caseFile?.conversation_stage !== "classified"
      ? parseQuickOptions(lastAgentEntry.text)
      : null;
  // A document upload already shows its own in-progress card (see
  // ConversationMessage's "document-uploading" kind) - don't also show the
  // generic "Thinking…" indicator underneath it.
  const showThinking = busy && entries[entries.length - 1]?.kind !== "document-uploading";

  return (
    <div className="ds-overview">
      {error && (
        <div className="ds-overview__error" role="alert">
          {error}
        </div>
      )}
      <div className="ds-overview__conversation">
        {/* A blank panel leaves the reader unable to tell "nothing was
            said" from "this failed to load" - most visible to a reviewer
            opening a project whose facts were entered directly rather
            than through the conversation. */}
        {entries.length === 0 && !busy && !error && (
          <p className="ds-overview__empty">
            {readOnly
              ? "No conversation was recorded for this project — its facts were entered directly on the Case File page."
              : "Nothing has been said yet."}
          </p>
        )}
        {entries.map((entry) => (
          <ConversationMessage key={entry.id} entry={entry} />
        ))}
        {showThinking && (
          <div className="ds-overview__thinking" aria-live="polite">
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {quickOptions && (
        <div className="ds-overview__quick-options" role="group" aria-label="Suggested answers">
          {quickOptions.map((option) => (
            <button key={option} type="button" className="ds-overview__quick-option" onClick={() => handleSend(option)} disabled={busy || readOnly}>
              {option}
            </button>
          ))}
        </div>
      )}
      {/* A reviewer can read someone else's project but not add to it -
          the server refuses (Access.WRITE), so the UI must not invite them
          into a 403 with a composer that looks live. */}
      <Composer
        onSend={handleSend}
        onUploadDocument={handleUploadDocument}
        disabled={busy || readOnly}
        placeholder={
          readOnly
            ? "You're reviewing this project — only its owner can continue the conversation."
            : busy
              ? "Waiting for a response…"
              : "Type your answer…"
        }
      />
    </div>
  );
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return "Could not reach the backend. Is it running?";
    return `Something went wrong (${err.status}). ${err.message}`;
  }
  if (err instanceof TypeError) {
    return "Could not reach the backend — check it's running and VITE_API_BASE_URL is correct.";
  }
  return "Something went wrong. Please try again.";
}
