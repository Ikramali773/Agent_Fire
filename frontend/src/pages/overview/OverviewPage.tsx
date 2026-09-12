import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { CaseFile } from "../../types";
import { Composer } from "./Composer";
import { ConversationMessage } from "./ConversationMessage";
import { nextEntryId, type ConversationEntry } from "./conversation";
import { normalizeClassification } from "../../lib/caseFileFields";
import { parseQuickOptions } from "../../lib/quickOptions";
import "./OverviewPage.css";

interface Props {
  caseFile: CaseFile | null;
  onCaseFileChange: (caseFile: CaseFile) => void;
  onBusyChange: (busy: boolean) => void;
}

// The AI compliance workspace - a copilot over the Case File, not the whole
// application. Keeps using the exact same conversational API (create /
// start / message / documents) as before; this file only changes how that
// exchange is presented.
export function OverviewPage({ caseFile, onCaseFileChange, onBusyChange }: Props) {
  const [entries, setEntries] = useState<ConversationEntry[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const initialized = useRef(false);

  useEffect(() => {
    onBusyChange(busy);
  }, [busy, onBusyChange]);

  useEffect(() => {
    if (initialized.current) return; // React StrictMode double-invokes effects in dev
    initialized.current = true;

    (async () => {
      try {
        const created = await api.createCaseFile();
        const started = await api.startConversation(created.session_id);
        onCaseFileChange(started.case_file);
        setEntries([{ kind: "agent", id: nextEntryId(), text: started.agent_message }]);
      } catch (err) {
        setError(describeError(err));
      } finally {
        setBusy(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  const handleSend = useCallback(
    async (text: string) => {
      if (!caseFile) return;
      setEntries((prev) => [...prev, { kind: "user", id: nextEntryId(), text }]);
      setBusy(true);
      setError(null);
      try {
        const previousStage = caseFile.conversation_stage;
        const result = await api.sendMessage(caseFile.session_id, text);
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
    [caseFile, onCaseFileChange],
  );

  const handleUploadDocument = useCallback(
    async (file: File) => {
      if (!caseFile) return;
      setError(null);
      try {
        const result = await api.uploadDocument(caseFile.session_id, file);
        onCaseFileChange(result.case_file);
        setEntries((prev) => [...prev, { kind: "document-result", id: nextEntryId(), fileName: file.name, summary: result.summary }]);
      } catch (err) {
        setError(describeError(err));
      }
    },
    [caseFile, onCaseFileChange],
  );

  const lastAgentEntry = [...entries].reverse().find((entry) => entry.kind === "agent");
  const quickOptions =
    !busy && lastAgentEntry && lastAgentEntry.kind === "agent" && caseFile && caseFile.conversation_stage !== "classified"
      ? parseQuickOptions(lastAgentEntry.text)
      : null;

  return (
    <div className="ds-overview">
      {error && (
        <div className="ds-overview__error" role="alert">
          {error}
        </div>
      )}
      <div className="ds-overview__conversation">
        {entries.map((entry) => (
          <ConversationMessage key={entry.id} entry={entry} />
        ))}
        {busy && (
          <div className="ds-overview__thinking" aria-live="polite">
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {quickOptions && (
        <div className="ds-overview__quick-options" role="group" aria-label="Suggested answers">
          {quickOptions.map((option) => (
            <button key={option} type="button" className="ds-overview__quick-option" onClick={() => handleSend(option)} disabled={busy}>
              {option}
            </button>
          ))}
        </div>
      )}
      <Composer onSend={handleSend} onUploadDocument={handleUploadDocument} disabled={busy} placeholder={busy ? "Waiting for a response…" : "Type your answer…"} />
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
