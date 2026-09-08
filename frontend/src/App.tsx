import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import { api, ApiError } from "./api/client";
import { CaseSummaryPanel } from "./components/CaseSummaryPanel";
import { ChatWindow } from "./components/ChatWindow";
import { ReportView } from "./components/ReportView";
import type { CaseFile, ChatMessage } from "./types";

const DISCLAIMER =
  "Advisory only — not a statutory approval. Confirm with a licensed fire consultant before filing.";

function App() {
  const [caseFile, setCaseFile] = useState<CaseFile | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return; // React StrictMode double-invokes effects in dev
    initialized.current = true;

    (async () => {
      try {
        const created = await api.createCaseFile();
        const started = await api.startConversation(created.session_id);
        setCaseFile(started.case_file);
        setMessages([{ role: "agent", text: started.agent_message }]);
      } catch (err) {
        setError(describeError(err));
      } finally {
        setBusy(false);
      }
    })();
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      if (!caseFile) return;
      setMessages((prev) => [...prev, { role: "user", text }]);
      setBusy(true);
      setError(null);
      try {
        const result = await api.sendMessage(caseFile.session_id, text);
        setCaseFile(result.case_file);
        setMessages((prev) => [...prev, { role: "agent", text: result.agent_message }]);
      } catch (err) {
        setError(describeError(err));
      } finally {
        setBusy(false);
      }
    },
    [caseFile],
  );

  const handleOpenReport = useCallback(async () => {
    if (!caseFile) return;
    setReportOpen(true);
    setReportLoading(true);
    try {
      const { markdown } = await api.getReport(caseFile.session_id);
      setReportMarkdown(markdown);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setReportLoading(false);
    }
  }, [caseFile]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Fire Safety &amp; NOC Readiness Assistant</h1>
        <p className="app-header__subtitle">NBCS 2026 Part F — Phase 1</p>
      </header>

      {error && (
        <div className="app-error" role="alert">
          {error}
        </div>
      )}

      <main className="app-main">
        <ChatWindow
          messages={messages}
          onSend={handleSend}
          disabled={busy}
          placeholder={busy ? "Waiting for a response…" : "Type your answer…"}
        />
        <CaseSummaryPanel caseFile={caseFile} />
      </main>

      {caseFile?.conversation_stage === "classified" && (
        <div className="app-report-cta">
          <button onClick={handleOpenReport}>View full report</button>
        </div>
      )}

      <footer className="app-footer">{DISCLAIMER}</footer>

      {reportOpen && (
        <ReportView
          markdown={reportMarkdown}
          loading={reportLoading}
          onClose={() => setReportOpen(false)}
        />
      )}
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

export default App;
