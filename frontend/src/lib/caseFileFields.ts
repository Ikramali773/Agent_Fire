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

/** A human label for a project in a list, when it may not be named yet.
 *
 * The project name is collected partway through the intake, so a brand-new
 * chat has none - and a rail of identical "Untitled project" rows is
 * useless. Falls back to whatever else identifies the project, in
 * decreasing order of how well it does so:
 *
 * 1. the name the user gave it;
 * 2. what they opened the conversation with (`chatTitle`, from
 *    GET /users/me/chat-titles) - "a twelve storey hospital in Pune" says
 *    far more than the city alone;
 * 3. the location, then the occupancy, from the case file itself.
 */
export function projectLabel(caseFile: CaseFile, chatTitle?: string): string {
  if (caseFile.project_name) return caseFile.project_name;
  if (chatTitle) return chatTitle;
  const place = [caseFile.city, caseFile.state].filter(Boolean).join(", ");
  if (place) return place;
  if (caseFile.occupancy_type) return formatLabel(caseFile.occupancy_type);
  return "Untitled project";
}
