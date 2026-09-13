"""Human review data contract - Phase 3.

The classifier has always been able to say "a person has to look at this"
(`ClassificationResult.require_human_review_flag`), and says so in 15
different situations. Until Phase 3 that flag was a dead end: nothing
listed flagged cases, tracked whether anyone looked, or recorded what they
concluded.

Two separate things live here, and the separation is the point:

- `ReviewReason` is the ENGINE's output - why this case cannot be
  finished automatically. It is derived, never entered by a person, and it
  is part of the classification result.
- `ReviewEvent` is a PERSON's output - what a reviewer concluded. It lives
  in its own append-only table and never rewrites the classification.

That second rule is load-bearing, not a style preference. The product
scope's Part G Principle 1 is "LLM reasons and explains; deterministic
engines decide" - letting a human hand-edit the engine's verdict breaks it
exactly as surely as letting the LLM do it. A reviewer who believes the
output is wrong changes the FACTS (the Case File), and the engine
reclassifies from those. Their opinion is recorded alongside the
classification, never on top of it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReviewReasonCode(str, Enum):
    """Why the engine could not finish on its own.

    Typed rather than left as prose so the review queue can group and
    filter by it - "3 cases blocked on a not-permitted combination" is
    actionable in a way that three paragraphs of notes are not. The prose
    is still carried in `ReviewReason.detail`.
    """

    MANDATORY_OCCUPANCY = "mandatory_occupancy"
    """Institutional or Hazardous: never automated, whatever the facts say."""

    NO_BAND_MATCHED = "no_band_matched"
    """No Table 7 band covers this height/area combination."""

    CLASSIFICATION_ERROR = "classification_error"
    """The Table 7 lookup could not run - usually a missing required fact."""

    NOT_PERMITTED_COMBINATION = "not_permitted_combination"
    """Group K marks this pair of occupancies NP (not permitted)."""

    MISSING_SEPARATION_RATING = "missing_separation_rating"
    """No fire-separation rating exists between two components present."""

    INCOMPLETE_MIXED_BREAKDOWN = "incomplete_mixed_breakdown"
    """A Mixed Use building was declared with fewer than two components."""

    INVALID_MIXED_COMPONENT = "invalid_mixed_component"
    """A Mixed Use component was itself given as "Mixed Use"."""

    AMBIGUOUS_BAND = "ambiguous_band"
    """More than one Table 7 band matched; the first was used but the others need checking."""

    MISSING_COMPONENT_AREA = "missing_component_area"
    """A Mixed Use component has no floor area, so it cannot be classified."""


class ReviewReason(BaseModel):
    code: ReviewReasonCode
    detail: str = Field(
        description="The human-readable explanation, identical to the matching entry in notes."
    )


class ReviewStatus(str, Enum):
    """Where a flagged case is in its review.

    `NEEDS_REVIEW` is the implicit starting state of any flagged case - it
    is never written as an event, it is simply what a case with no review
    events yet is. Everything else is a person's recorded decision.
    """

    NEEDS_REVIEW = "needs_review"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


# Statuses a person is allowed to record. NEEDS_REVIEW is excluded: it is
# derived from "no events yet", so accepting it as a verdict would let a
# review be silently rewound and make the history lie about what happened.
RECORDABLE_STATUSES = frozenset(
    {
        ReviewStatus.IN_REVIEW,
        ReviewStatus.APPROVED,
        ReviewStatus.CHANGES_REQUESTED,
        ReviewStatus.REJECTED,
    }
)


class ReviewEvent(BaseModel):
    id: int
    session_id: str
    status: ReviewStatus
    note: str = Field(default="", description="The reviewer's own words. Free text, never parsed.")
    actor_user_id: Optional[str] = None
    actor_email: Optional[str] = Field(
        default=None,
        description=(
            "The reviewer's email as it was at the time, stored alongside the id. A sign-off "
            "has to stay attributable years later even if the account is renamed or removed."
        ),
    )
    created_at: datetime


class ReviewState(BaseModel):
    """Everything the Review page needs for one case, in one response."""

    session_id: str
    project_name: str = ""
    requires_review: bool = Field(
        description="The engine's flag - whether a person is required to look at this at all."
    )
    reasons: list[ReviewReason] = Field(default_factory=list)
    status: ReviewStatus
    events: list[ReviewEvent] = Field(default_factory=list)
    flagged_at: Optional[datetime] = Field(
        default=None,
        description="When the case file was last updated - what the queue orders by.",
    )
    can_record_verdict: bool = Field(
        default=False,
        description="Whether the calling user may record a verdict (owner or granted reviewer).",
    )
