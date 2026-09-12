import "./SourceBadge.css";

// Mirrors the backend's FieldSourceKind exactly (user/document/inferred/
// unknown) - see backend/app/models/case_file.py. "geometry" is reserved
// for Phase 4 (Building Digital Model derived facts) and renders with the
// same visual treatment as "inferred" until that source type exists.
export type FieldSourceKind = "user" | "document" | "inferred" | "unknown" | "geometry";

const LABELS: Record<FieldSourceKind, string> = {
  user: "User",
  document: "Document",
  inferred: "Inferred",
  geometry: "Geometry",
  unknown: "Not yet provided",
};

interface Props {
  source: FieldSourceKind;
  confidence?: number | null;
}

export function SourceBadge({ source, confidence }: Props) {
  const pct = typeof confidence === "number" ? Math.round(confidence * 100) : null;
  return (
    <span className={`ds-source-badge ds-source-badge--${source}`}>
      {LABELS[source]}
      {pct !== null && source !== "unknown" && (
        <span className="ds-source-badge__confidence tabular-nums">{pct}%</span>
      )}
    </span>
  );
}
