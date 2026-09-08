import ReactMarkdown from "react-markdown";

interface Props {
  markdown: string | null;
  loading: boolean;
  onClose: () => void;
}

export function ReportView({ markdown, loading, onClose }: Props) {
  return (
    <div className="report-overlay" role="dialog" aria-label="Fire safety report">
      <div className="report-panel">
        <div className="report-panel__header">
          <h2>Fire Safety & NOC Readiness Report</h2>
          <button onClick={onClose} aria-label="Close report">
            ×
          </button>
        </div>
        <div className="report-panel__body">
          {loading && <p>Loading report…</p>}
          {!loading && markdown && <ReactMarkdown>{markdown}</ReactMarkdown>}
          {!loading && !markdown && <p>No report available yet.</p>}
        </div>
      </div>
    </div>
  );
}
