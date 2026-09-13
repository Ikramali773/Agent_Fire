import type { Status } from "../design-system/components/StatusPill";
import type { RequirementStatus } from "../types";

// Maps a requirement outcome onto the product's one status vocabulary
// (StatusPill), so the meaning of each icon never has to be relearned.
//
// `met` is INFO, not PASS. The system knows an installation was declared;
// it does not know that it exists, covers the right areas, or is correctly
// designed. Rendering that as a green pass would be the product asserting
// compliance it has not established - which the footer on every page
// explicitly disclaims.
const TONES: Record<string, Status> = {
  met: "info",
  not_met: "fail",
  unknown: "unknown",
  not_required: "info",
};

export function findingTone(status: RequirementStatus | string): Status {
  return TONES[status] ?? "unknown";
}

const LABELS: Record<string, string> = {
  met: "Declared",
  not_met: "Not declared",
  unknown: "Not known",
  not_required: "Not required",
};

export function findingLabel(status: RequirementStatus | string): string {
  return LABELS[status] ?? status;
}

/** The headline for a set of findings: the worst thing in it. */
export function findingsSummaryTone(notMet: number, unknown: number): Status {
  if (notMet > 0) return "fail";
  if (unknown > 0) return "unknown";
  return "info";
}
