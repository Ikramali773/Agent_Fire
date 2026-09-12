import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import { Card } from "../../design-system/components/Card";
import { DocumentResultCard } from "../../design-system/components/DocumentResultCard";
import { EmptyState } from "../../design-system/components/EmptyState";
import { ProgressSteps } from "../../design-system/components/ProgressSteps";
import type { CaseFile, IngestSummary } from "../../types";
import "./DocumentsPage.css";

const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg"];
const UPLOADING_STEPS = [
  { key: "uploaded", label: "Uploaded" },
  { key: "reading", label: "Reading" },
  { key: "extracting", label: "Extracting" },
  { key: "confidence", label: "Checking confidence" },
  { key: "ready", label: "Ready" },
];

interface UploadInFlight {
  fileName: string;
}

interface UploadResult {
  fileName: string;
  summary: IngestSummary;
}

interface Props {
  caseFile: CaseFile | null;
  onCaseFileChange: (caseFile: CaseFile) => void;
}

export function DocumentsPage({ caseFile, onCaseFileChange }: Props) {
  const [inFlight, setInFlight] = useState<UploadInFlight | null>(null);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = async (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file || !caseFile) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Please upload a PDF, PNG, or JPEG file.");
      return;
    }
    setError(null);
    setInFlight({ fileName: file.name });
    try {
      const result = await api.uploadDocument(caseFile.session_id, file);
      onCaseFileChange(result.case_file);
      setResults((prev) => [{ fileName: file.name, summary: result.summary }, ...prev]);
    } catch (err) {
      setError(err instanceof ApiError ? `Could not process that file (${err.status}). ${err.message}` : "Could not process that file.");
    } finally {
      setInFlight(null);
    }
  };

  if (!caseFile) {
    return (
      <div className="ds-documents-page">
        <EmptyState title="No active case yet" description="Start a conversation on the Overview page before uploading documents." />
      </div>
    );
  }

  return (
    <div className="ds-documents-page">
      <header className="ds-documents-page__header">
        <h1>Documents</h1>
        <p>Upload plans, NOC letters, or certificates. Each file is read, extracted, and checked for confidence before it's added to the case file.</p>
      </header>

      {error && (
        <div className="ds-documents-page__error" role="alert">
          {error}
        </div>
      )}

      <div
        className={`ds-documents-page__dropzone${dragActive ? " ds-documents-page__dropzone--active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          className="ds-documents-page__file-input"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <Upload className="ds-documents-page__dropzone-icon" aria-hidden="true" />
        <p className="ds-documents-page__dropzone-text">Drag a file here, or click to browse</p>
        <p className="ds-documents-page__dropzone-hint">PDF, PNG, or JPEG</p>
      </div>

      {inFlight && (
        <Card title={inFlight.fileName}>
          <ProgressSteps steps={UPLOADING_STEPS} activeIndex={1} />
        </Card>
      )}

      {results.length > 0 && (
        <div className="ds-documents-page__results">
          {results.map((result, index) => (
            <DocumentResultCard key={index} fileName={result.fileName} summary={result.summary} />
          ))}
        </div>
      )}

      {caseFile.source_documents.length > 0 && (
        <Card title="All source documents">
          <table className="ds-documents-page__table">
            <thead>
              <tr>
                <th>File</th>
                <th>Pages</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {caseFile.source_documents.map((doc, index) => (
                <tr key={index}>
                  <td>{doc.filename}</td>
                  <td className="tabular-nums">{doc.pages}</td>
                  <td className="tabular-nums">{Math.round(doc.overall_confidence * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
