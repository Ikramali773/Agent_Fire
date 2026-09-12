import type { Status } from "../../design-system/components/StatusPill";
import type { ClassificationResult } from "../../types";

// Pure presentation mapping over the existing ClassificationResult - no new
// compliance logic, no invented pass/fail verdicts. Phase 1's classifier
// only determines WHICH Table 7 clauses apply, not whether the building
// actually satisfies each one (that per-requirement evaluation is Phase 3's
// rule engine and Phase 4's compliance engine). So every applicable clause
// is honestly "unknown" here until that engine exists; the one place a real
// verdict-shaped signal exists today is require_human_review_flag.
export function overallStatus(result: ClassificationResult): Status {
  if (result.require_human_review_flag) return "human_review";
  if (result.applies === null) return "unknown";
  return "info";
}

export function clauseStatus(result: ClassificationResult): Status {
  return result.require_human_review_flag ? "human_review" : "unknown";
}
