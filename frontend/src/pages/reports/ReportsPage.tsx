import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, ApiError } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { EmptyState } from "../../design-system/components/EmptyState";
import type { CaseFile } from "../../types";
import "./ReportsPage.css";

interface Props {
  caseFile: CaseFile | null;
}

export function ReportsPage({ caseFile }: Props) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = caseFile?.conversation_stage === "classified";

  useEffect(() => {
    if (!caseFile || !ready) return;
    setLoading(true);
    setError(null);
    api
      .getReport(caseFile.session_id)
      .then((res) => setMarkdown(res.markdown))
      .catch((err) => setError(err instanceof ApiError ? `Could not load the report (${err.status}).` : "Could not load the report."))
      .finally(() => setLoading(false));
  }, [caseFile, ready]);

  if (!caseFile || !ready) {
    return (
      <div className="ds-reports-page">
        <EmptyState
          title="Report not ready yet"
          description="A report becomes available once the building has been classified. Continue the conversation on the Overview page."
        />
      </div>
    );
  }

  return (
    <div className="ds-reports-page">
      <header className="ds-reports-page__header">
        <div>
          <h1>Fire Safety &amp; NOC Readiness Report</h1>
          <p>{caseFile.project_name || "Untitled project"}</p>
        </div>
        <div className="ds-reports-page__actions">
          <Button variant="secondary" size="sm" disabled title="Coming in Phase 2">
            Download PDF
          </Button>
          <Button variant="secondary" size="sm" disabled title="Coming in Phase 2">
            Download DOCX
          </Button>
        </div>
      </header>

      {error && (
        <div className="ds-reports-page__error" role="alert">
          {error}
        </div>
      )}

      <div className="ds-reports-page__document">
        {loading && <p className="ds-reports-page__loading">Loading report…</p>}
        {!loading && markdown && (
          <div className="ds-reports-page__markdown">
            <ReactMarkdown>{markdown}</ReactMarkdown>
          </div>
        )}
        {!loading && !markdown && !error && <p className="ds-reports-page__loading">No report available yet.</p>}
      </div>
    </div>
  );
}
