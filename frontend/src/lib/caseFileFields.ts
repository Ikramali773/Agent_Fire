import type { CaseFile, ClassificationResult } from "../types";
import type { FieldSourceKind } from "../design-system/components/SourceBadge";

export interface FieldMeta {
  source?: FieldSourceKind;
  confidence?: number | null;
}

// Look up the provenance the backend recorded for one Case File field, e.g.
// fieldMeta(caseFile, "height_m"). Used by every surface that shows a
// building fact so provenance/confidence is never invented on the frontend.
export function fieldMeta(caseFile: CaseFile, key: string): FieldMeta {
  const entry = caseFile.field_sources?.[key];
  if (!entry) return {};
  return { source: entry.source as FieldSourceKind, confidence: entry.confidence };
}

export function formatValue(value: unknown, fallback = "Not yet known"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (Array.isArray(value)) return value.length ? value.join(", ") : fallback;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function formatLabel(raw?: string | null): string {
  if (!raw) return "Not yet known";
  return raw
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// CaseFile["classification_result"] carries its own (raw, partly-optional)
// schema type rather than the Required<> one exported as ClassificationResult
// below - Required<> only strips optionality from CaseFile's own top-level
// keys, not recursively from the objects those keys point to. The backend
// still always serializes every field (Pydantic never omits one), so this
// just fills in the same defaults Required<> assumes at the top level.
export function normalizeClassification(raw: CaseFile["classification_result"]): ClassificationResult {
  return {
    applies: raw.applies ?? null,
    table_7_ref: raw.table_7_ref,
    applicable_clauses: raw.applicable_clauses ?? [],
    applicable_state_checklist_id: raw.applicable_state_checklist_id ?? null,
    is_high_rise: raw.is_high_rise ?? null,
    require_human_review_flag: raw.require_human_review_flag,
    protection_level: raw.protection_level ?? null,
    notes: raw.notes ?? [],
  };
}
