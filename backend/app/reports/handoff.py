"""Consultant handoff package - Phase 3.

When the engine says "a person has to look at this", the product's answer
is to hand the case to a licensed fire consultant. The report alone is not
enough for that: it states conclusions, and the question a professional
putting their name to a sign-off actually asks is "where did each of these
numbers come from, and what has changed since?".

So the handoff is the report plus the three things only this system knows:

- WHY review is required, from the engine's own typed reasons;
- WHERE every fact came from - user-confirmed, extracted from a drawing at
  some OCR confidence, or inferred. All of this has been recorded in
  `field_sources` since Phase 1 and no export has ever surfaced it, which
  is exactly the gap a reviewer falls into;
- WHAT has changed and when, from the Phase 2 change log, so a reviewer can
  see that the height was 24 m until a drawing was uploaded yesterday.

No new facts are invented here. Like generator.py, this module only
restates what is already recorded.
"""

from __future__ import annotations

from app.models.case_file import CaseFile, FieldSourceKind
from app.models.change_log import FieldChange
from app.models.review import ReviewState, ReviewStatus
from app.reports.generator import generate_report_markdown

_SOURCE_LABEL = {
    FieldSourceKind.USER: "Confirmed by user",
    FieldSourceKind.DOCUMENT: "Extracted from document",
    FieldSourceKind.INFERRED: "Inferred",
    FieldSourceKind.UNKNOWN: "Unknown",
}

_STATUS_LABEL = {
    ReviewStatus.NEEDS_REVIEW: "Needs review - nobody has picked this up yet",
    ReviewStatus.IN_REVIEW: "In review",
    ReviewStatus.APPROVED: "Approved by reviewer",
    ReviewStatus.CHANGES_REQUESTED: "Changes requested",
    ReviewStatus.REJECTED: "Rejected by reviewer",
}

_CHANGE_SOURCE_LABEL = {
    "user": "Edited directly",
    "dialogue": "From the conversation",
    "document": "From a document",
    "system": "System",
}


def _escape_cell(value: object) -> str:
    """Pipes inside a markdown table cell would split it into extra columns."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _review_reason_lines(review: ReviewState) -> list[str]:
    lines = ["## Why this case requires human review", ""]
    if not review.requires_review:
        lines.append(
            "The deterministic engine did **not** flag this case for mandatory review. "
            "It is being reviewed at the owner's request."
        )
        lines.append("")
        return lines
    lines.append(
        "The deterministic engine flagged this case. Each item below is a specific "
        "reason it could not be completed automatically - not a general caveat."
    )
    lines.append("")
    for reason in review.reasons:
        lines.append(f"- **{reason.code.value}** - {reason.detail}")
    lines.append("")
    return lines


def _review_status_lines(review: ReviewState) -> list[str]:
    lines = ["## Review status", "", f"**{_STATUS_LABEL[review.status]}**", ""]
    if not review.events:
        lines.append("No verdict has been recorded yet.")
        lines.append("")
        return lines
    lines.append("| When | Verdict | Reviewer | Note |")
    lines.append("| --- | --- | --- | --- |")
    for event in review.events:
        lines.append(
            "| {when} | {status} | {who} | {note} |".format(
                when=event.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                status=_escape_cell(event.status.value),
                who=_escape_cell(event.actor_email or "Anonymous session"),
                note=_escape_cell(event.note or "-"),
            )
        )
    lines.append("")
    lines.append(
        "_A reviewer's verdict is recorded alongside the classification and never replaces it. "
        "Where a reviewer disagreed, the underlying facts were changed and the engine "
        "reclassified from them - see the change history below._"
    )
    lines.append("")
    return lines


def _provenance_lines(case_file: CaseFile) -> list[str]:
    lines = ["## Where every fact came from", ""]
    if not case_file.field_sources:
        lines.append("No provenance has been recorded for this case file.")
        lines.append("")
        return lines
    lines.append(
        "Confidence is the extraction pipeline's own, for facts read out of a document. "
        "A fact confirmed by the user carries no extraction confidence."
    )
    lines.append("")
    lines.append("| Field | Value | Source | Confidence |")
    lines.append("| --- | --- | --- | --- |")
    for field in sorted(case_file.field_sources):
        source = case_file.field_sources[field]
        confidence = (
            f"{round(source.confidence * 100)}%"
            if source.source is FieldSourceKind.DOCUMENT and source.confidence
            else "-"
        )
        lines.append(
            f"| {_escape_cell(field)} | {_escape_cell(source.value)} "
            f"| {_SOURCE_LABEL[source.source]} | {confidence} |"
        )
    lines.append("")
    return lines


def _change_history_lines(changes: list[FieldChange], total: int | None = None) -> list[str]:
    lines = ["## Change history", ""]
    if not changes:
        lines.append("Nothing has been changed since this case file was created.")
        lines.append("")
        return lines
    # A compliance document that quietly drops entries is worse than one
    # that says how many it is showing. The reader can go to the app for
    # the rest; they cannot know to do that if the pack never tells them.
    if total is not None and total > len(changes):
        lines.append(
            f"**Showing the {len(changes)} most recent of {total} changes.** "
            "The full history is on the project's Case File page."
        )
        lines.append("")
    lines.append("| When | Field | From | To | Source |")
    lines.append("| --- | --- | --- | --- | --- |")
    # Oldest first: in a document this reads as a narrative, where the live
    # timeline in the app is newest-first for "what changed recently".
    for change in sorted(changes, key=lambda item: item.id):
        lines.append(
            "| {when} | {field} | {old} | {new} | {source} |".format(
                when=change.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                field=_escape_cell(change.field),
                old=_escape_cell("Not set" if change.old_value in (None, "") else change.old_value),
                new=_escape_cell("Not set" if change.new_value in (None, "") else change.new_value),
                source=_CHANGE_SOURCE_LABEL.get(change.source.value, change.source.value),
            )
        )
    lines.append("")
    return lines


def generate_handoff_markdown(
    case_file: CaseFile,
    review: ReviewState,
    changes: list[FieldChange],
    total_changes: int | None = None,
) -> str:
    """The full package: the report, then everything a reviewer needs to
    judge whether to trust it.
    """
    parts = [
        generate_report_markdown(case_file),
        "",
        "---",
        "",
        "# Reviewer handoff pack",
        "",
        "Everything below is context for the reviewer. It restates what this system "
        "recorded; it contains no additional analysis and no new facts.",
        "",
    ]
    parts += _review_reason_lines(review)
    parts += _review_status_lines(review)
    parts += _provenance_lines(case_file)
    parts += _change_history_lines(changes, total_changes)
    return "\n".join(parts).rstrip() + "\n"
