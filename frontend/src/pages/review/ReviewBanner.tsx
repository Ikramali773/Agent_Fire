import { ShieldAlert } from "lucide-react";
import { Button } from "../../design-system/components/Button";
import { reviewReasonLabel } from "../../lib/review";
import type { ClassificationResult } from "../../types";
import "./ReviewBanner.css";

interface Props {
  result: ClassificationResult;
  onGoToReview: () => void;
}

// Review is a page nobody visits unless something sends them there, and a
// flagged case that never gets reviewed is the failure mode this whole
// phase exists to prevent. So the flag is surfaced where users already
// look at the classification - and it says WHY, using the engine's typed
// reasons, rather than a bare "needs review" that reads as boilerplate.
export function ReviewBanner({ result, onGoToReview }: Props) {
  if (!result.require_human_review_flag) return null;
  const reasons = result.review_reasons ?? [];

  return (
    <div className="ds-review-banner" role="note">
      <ShieldAlert className="ds-review-banner__icon" aria-hidden="true" />
      <div className="ds-review-banner__body">
        <p className="ds-review-banner__title">A person has to look at this case</p>
        <p className="ds-review-banner__text">
          {reasons.length > 0
            ? reasons.map((reason) => reviewReasonLabel(reason.code)).join(" · ")
            : "The classifier could not complete this case on its own."}
        </p>
      </div>
      <Button variant="secondary" size="sm" onClick={onGoToReview}>
        Open review
      </Button>
    </div>
  );
}
