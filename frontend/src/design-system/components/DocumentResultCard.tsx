import { FileWarning } from "lucide-react";
import type { IngestSummary } from "../../types";
import { Badge } from "./Badge";
import { ProgressSteps } from "./ProgressSteps";
import { StatusPill } from "./StatusPill";
import "./DocumentResultCard.css";

const DOCUMENT_PROCESSING_STEPS = [
  { key: "uploaded", label: "Uploaded" },
  { key: "reading", label: "Reading" },
  { key: "extracting", label: "Extracting" },
  { key: "confidence", label: "Checking confidence" },
  { key: "ready", label: "Ready" },
];

interface Props {
  fileName: string;
  summary: IngestSummary;
}

// Real extraction results for one uploaded document - never a silent
// "done" spinner. Shared between the Overview conversation and the
// Documents page so the same file shows up looking the same everywhere.
export function DocumentResultCard({ fileName, summary }: Props) {
  const failed = summary.tier_used === 0;
  return (
    <div className="ds-doc-result">
      <div className="ds-doc-result__header">
        <span className="ds-doc-result__title">{fileName}</span>
        {failed ? (
          <StatusPill status="fail" label="Could not read" size="sm" />
        ) : summary.needs_human_review ? (
          <StatusPill status="human_review" size="sm" />
        ) : (
          <StatusPill status="pass" label="Extracted" size="sm" />
        )}
      </div>
      {!failed && (
        <div className="ds-doc-result__steps">
          <ProgressSteps steps={DOCUMENT_PROCESSING_STEPS} activeIndex={DOCUMENT_PROCESSING_STEPS.length} />
        </div>
      )}
      <div className="ds-doc-result__body">
        {failed && (
          <p className="ds-doc-result__note">
            <FileWarning aria-hidden="true" className="ds-doc-result__note-icon" />
            {summary.failure_reason ?? "Unknown error reading this file."}
          </p>
        )}
        {!failed && summary.fields_extracted.length > 0 && (
          <div className="ds-doc-result__fields">
            {summary.fields_extracted.map((field) => (
              <Badge key={field}>{field.replace(/_/g, " ")}</Badge>
            ))}
          </div>
        )}
        {!failed && summary.fields_extracted.length === 0 && (
          <p className="ds-doc-result__note">
            {summary.fact_extraction_skipped_reason ?? "No details could be confidently extracted from this file."}
          </p>
        )}
        {!failed && summary.needs_human_review && summary.fields_extracted.length > 0 && (
          <p className="ds-doc-result__note">This was a lower-confidence read (tier {summary.tier_used}) — please double-check it.</p>
        )}
      </div>
    </div>
  );
}
