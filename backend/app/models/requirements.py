"""Per-requirement compliance findings - Phase 4.

Phase 1's classifier determines WHICH requirements apply to a building. It
has never determined whether the building actually MEETS them, which is why
every clause on the Compliance page has shown an undifferentiated
"unknown" since it was built. This is the contract for the layer that
closes that gap.

What a finding is, precisely: one firefighting installation that the
matched Table 7 band marks required, compared against what the building
has been recorded as having. That comparison is deterministic and fully
traceable - the requirement comes from the digitized rule data, the
evidence comes from the Case File, and nothing in between is inferred.

What a finding is NOT: a judgement about whether an installation is
adequate, correctly specified, or correctly installed. The system knows a
sprinkler system was declared; it does not know its coverage, spacing or
hydraulic design. Every surface that shows these must keep saying so.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RequirementStatus(str, Enum):
    """The outcome of comparing one requirement against the Case File."""

    MET = "met"
    """Required, and the building declared it."""

    NOT_MET = "not_met"
    """Required, and it is absent from a non-empty declared inventory."""

    UNKNOWN = "unknown"
    """Required, but nothing has been declared - so nobody can say either way.

    Deliberately distinct from NOT_MET. Reporting a building as failing
    because nobody told us what it has would be a false verdict on a
    compliance record, and the difference between "you are missing a wet
    riser" and "we do not know whether you have one" is the difference
    between a defect and a question.
    """

    NOT_REQUIRED = "not_required"
    """The matched band marks this installation NR."""


class RequirementFinding(BaseModel):
    code: str = Field(description="The rule-data key, e.g. 'automatic_wet_sprinkler_system'.")
    label: str = Field(description="The same requirement in words, for display.")
    status: RequirementStatus
    required: bool
    detail: str = Field(description="Why this finding says what it says, in one sentence.")
    matched_declaration: str | None = Field(
        default=None,
        description="The entry in existing_fire_systems this was matched to, when it was met.",
    )


class RequirementReport(BaseModel):
    """Every finding for one case file, plus what could not be evaluated."""

    session_id: str
    evaluated: bool = Field(
        description="False when the building has not been classified, so nothing applies yet."
    )
    table_7_ref: str = ""
    protection_level: str | None = None
    findings: list[RequirementFinding] = Field(default_factory=list)
    unrecognized_declarations: list[str] = Field(
        default_factory=list,
        description=(
            "Entries in existing_fire_systems that could not be matched to a known "
            "installation. Surfaced rather than dropped: a system the engine did not "
            "understand is not the same as a system the building does not have, and "
            "silently ignoring it would make a requirement look unmet when it is not."
        ),
    )
    met_count: int = 0
    not_met_count: int = 0
    unknown_count: int = 0
