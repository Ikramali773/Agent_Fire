import type { Status } from "../design-system/components/StatusPill";
import type { ReviewReasonCode, ReviewStatus } from "../types";

// Why the engine could not finish on its own, phrased for a person rather
// than as the enum name. Mirrors backend/app/models/review.py's
// ReviewReasonCode; an unknown code (a newer backend against an older
// frontend) falls back to the code itself rather than rendering nothing.
const REASON_LABELS: Record<string, string> = {
  mandatory_occupancy: "Occupancy always needs an expert",
  no_band_matched: "No Table 7 band matched",
  classification_error: "A required fact is missing",
  not_permitted_combination: "Occupancy combination not permitted",
  missing_separation_rating: "No separation rating between occupancies",
  incomplete_mixed_breakdown: "Mixed Use breakdown incomplete",
  invalid_mixed_component: "Invalid Mixed Use component",
  ambiguous_band: "More than one Table 7 band matched",
  missing_component_area: "A component has no floor area",
};

export function reviewReasonLabel(code: ReviewReasonCode | string): string {
  return REASON_LABELS[code] ?? code;
}

const STATUS_LABELS: Record<string, string> = {
  needs_review: "Needs review",
  in_review: "In review",
  approved: "Approved",
  changes_requested: "Changes requested",
  rejected: "Rejected",
};

export function reviewStatusLabel(status: ReviewStatus | string): string {
  return STATUS_LABELS[status] ?? status;
}

// Maps a review status onto the product's one status vocabulary
// (StatusPill), so "what does this colour/icon mean" never has to be
// relearned on the Review page.
//
// `approved` is deliberately NOT `pass`: this product does not certify
// anything, and the footer on every page says so. It means "a named person
// signed this off", which is `info` plus their name - not a compliance
// pass the system is asserting.
const STATUS_TONES: Record<string, Status> = {
  needs_review: "human_review",
  in_review: "warning",
  approved: "info",
  changes_requested: "warning",
  rejected: "fail",
};

export function reviewStatusTone(status: ReviewStatus | string): Status {
  return STATUS_TONES[status] ?? "unknown";
}

/** Statuses a person can record - `needs_review` is the derived start state. */
export const RECORDABLE_STATUSES: ReviewStatus[] = [
  "in_review",
  "changes_requested",
  "approved",
  "rejected",
];
