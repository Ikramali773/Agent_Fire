"""Dialogue Manager - product scope section B.3 / B.5.

Drives the guided intake as a state machine over CaseFile.conversation_stage:

    INTAKE      -> ask each unfilled node from dialogue/nodes.py in order,
                   skipping anything already known (field_sources presence).
                   At any point, a message that isn't answering the pending
                   node routes to the Knowledge Q&A side-branch and then
                   returns to the same pending question (per B.5's "standing
                   side-branch" rule) - the tree is not a rigid blocking form.
    CONFIRMING  -> once every node is filled, show the case summary and ask
                   for confirmation. The reply is also opportunistically
                   re-extracted against every field, so a correction like
                   "actually it's 15 floors" is caught without a separate UI.
    CLASSIFIED  -> classify() has run; further messages are treated as
                   open Knowledge Q&A (the intake is done).

Node 2a (the upload nudge, now shown for every goal - originally
renewal-only) and Node 3a (the residential early-exit shortcut) are both
handled here rather than as dialogue/nodes.py Nodes: each is a one-off
message appended around an existing node transition, not a field to
collect - the actual "skip egress/existing_systems" logic for Node 3a lives
in those nodes' own `applicable` callbacks (residential_self_cert_eligible
in dialogue/nodes.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.dialogue.nodes import NODES, SUBDIVISION_OPTIONS, next_node, residential_self_cert_eligible
from app.engine.classifier import classify
from app.knowledge.context import build_qa_context
from app.llm.client import LLMClient, LLMNotConfiguredError, LLMUnavailableError
from app.models.case_file import CaseFile, ConversationStage, FieldSource, FieldSourceKind, Goal
from app.reports.generator import generate_report_markdown

OPENING_PROMPT = (
    "Hi — I can help you understand fire-safety requirements and NOC "
    "readiness for your building under NBCS 2026 Part F. Let's go through "
    "your building's details to see what applies to you. You can also ask "
    "me a general question at any point.\n\n"
)

# Node 2a, product scope §B.5, extended to every goal: right after the
# user says what they're trying to do, proactively point them at the upload
# widget (reuses the already-built OCR ingest pipeline, §B.7) instead of
# only supporting it as a passive button they have to notice on their own.
# Originally renewal-only; broadened since the upload speeds up every goal,
# not just renewal, and a user with a plan handy shouldn't have to guess
# that uploading is even an option.
_GOAL_UPLOAD_NUDGES: dict[Goal, str] = {
    Goal.RENEW_NOC: (
        "Since you're renewing an existing NOC, you can upload your existing NOC "
        "certificate or approved plan now (the 📎 attach button below) and I'll "
        "pull in whatever details it has — or just keep answering by hand.\n\n"
    ),
    Goal.PREP_NOC: (
        "If you have an approved plan or architectural drawing handy, you can "
        "upload it now (the 📎 attach button below) and I'll pull in whatever "
        "building details it has — or just keep answering by hand.\n\n"
    ),
    Goal.UNDERSTAND_REQUIREMENTS: (
        "If you have a building plan or drawing handy, you can upload it now "
        "(the 📎 attach button below) to speed this up — or just keep answering "
        "by hand.\n\n"
    ),
    Goal.GENERAL_QA: (
        "By the way, if you have a building plan handy, you can upload it any "
        "time (the 📎 attach button below) if it becomes relevant.\n\n"
    ),
}

# Node 3a: once a Residential building's height/area put it within Table
# 7A's self-certification threshold, the remaining egress/existing-systems
# questions no longer change the outcome (self-certification, not the full
# installation table, is what applies) - say so rather than silently
# skipping straight to confirmation with no explanation.
RESIDENTIAL_SELF_CERT_NUDGE = (
    "Good news — at this size, self-certification by a certified and "
    "State-approved building professional is accepted in place of the full "
    "installation requirements, so I don't need the remaining detail "
    "questions.\n\n"
)

# Node 3c: a per-component follow-up for Mixed Use occupancy_breakdown
# items that need a subdivision (per SUBDIVISION_OPTIONS) but don't have one
# yet - e.g. Node 3b's free-text answer named the occupancy ("Mercantile")
# without saying whether it's an underground shopping complex. Not a fixed
# dialogue/nodes.py Node since it targets one specific list item, chosen
# dynamically, rather than a fixed Case File field - handled as its own
# mini turn-handler below (_handle_mixed_use_subdivision_turn), the same
# pattern Node 2a/3a use for logic that doesn't fit the Node abstraction.
def _missing_subdivision_index(case_file: CaseFile) -> int | None:
    for index, item in enumerate(case_file.occupancy_breakdown):
        if item.type.value in SUBDIVISION_OPTIONS and not item.subdivision:
            return index
    return None


def _mixed_use_subdivision_prompt(item) -> str:
    options = SUBDIVISION_OPTIONS.get(item.type.value, {})
    return (
        f"For the {item.type.value} component ({item.floor_range}), which of these best "
        "describes it?\n" + "\n".join(f"- {code}: {label}" for code, label in options.items())
    )


def _mixed_use_subdivision_field_types(item) -> dict[str, type]:
    options = SUBDIVISION_OPTIONS.get(item.type.value, {})
    return {"occupancy_subdivision": Literal[tuple(options.keys())]}  # type: ignore[valid-type]


def _apply_mixed_use_subdivision(case_file: CaseFile, index: int, subdivision: str) -> CaseFile:
    updated_items = list(case_file.occupancy_breakdown)
    updated_items[index] = updated_items[index].model_copy(update={"subdivision": subdivision})
    case_file.occupancy_breakdown = updated_items
    case_file.updated_at = datetime.now(timezone.utc)
    return case_file


def _all_intake_fields_complete(case_file: CaseFile) -> bool:
    return _missing_subdivision_index(case_file) is None and next_node(case_file) is None


def _next_step_message(case_file: CaseFile) -> str:
    """What to ask/show next, given _all_intake_fields_complete(case_file) is
    False (the caller must check that first - this never returns the
    confirmation summary itself). Shared by the regular node path and the
    Node 3c subdivision follow-up path, since either can hand off to the
    other or to a plain node.
    """
    next_subdivision_index = _missing_subdivision_index(case_file)
    if next_subdivision_index is not None:
        return _mixed_use_subdivision_prompt(case_file.occupancy_breakdown[next_subdivision_index])
    next_pending = next_node(case_file)
    return next_pending.prompt(case_file)


_ALL_FIELD_TYPES = {name: typ for node in NODES for name, typ in node.field_types.items()}


@dataclass
class TurnResult:
    case_file: CaseFile
    agent_message: str


def _field_types_for(node, case_file: CaseFile) -> dict[str, type]:
    if node.id == "subdivision":
        options = SUBDIVISION_OPTIONS.get(
            case_file.occupancy_type.value if case_file.occupancy_type else "", {}
        )
        return {"occupancy_subdivision": Literal[tuple(options.keys())]}  # type: ignore[valid-type]
    return node.field_types


def _apply_extracted_fields(case_file: CaseFile, extracted: dict) -> CaseFile:
    if not extracted:
        return case_file
    merged = {**case_file.model_dump(), **extracted}
    updated = CaseFile.model_validate(merged)
    for field_name in extracted:
        updated.field_sources[field_name] = FieldSource(
            value=extracted[field_name], source=FieldSourceKind.USER, confidence=1.0
        )
    updated.updated_at = datetime.now(timezone.utc)
    return updated


def _format_occupancy_breakdown(items: list) -> str:
    parts = []
    for item in items:
        bit = f"{item.type.value} ({item.floor_range}"
        if item.floor_area_sqm is not None:
            bit += f", {item.floor_area_sqm} sqm"
        if item.subdivision:
            bit += f", {item.subdivision}"
        parts.append(bit + ")")
    return "; ".join(parts)


def _format_floor_wise_area(items: list) -> str:
    return "; ".join(f"{item.floor}: {item.area_sqm} sqm" for item in items)


def _format_field_value(name: str, value) -> str:
    if name == "occupancy_breakdown" and value:
        return _format_occupancy_breakdown(value)
    return str(value)


def _confirmation_summary(case_file: CaseFile) -> str:
    lines = ["Here's what I have so far:"]
    for name in _ALL_FIELD_TYPES:
        source = case_file.field_sources.get(name)
        value = getattr(case_file, name, None)
        if source is not None:
            lines.append(f"- {name}: {_format_field_value(name, value)}")
    # floor_wise_area/kitchen_count/door_count are document-upload-only (no
    # intake node asks for them - see dialogue/nodes.py's module docstring),
    # so they're never in _ALL_FIELD_TYPES above; shown here whenever a
    # document supplied one so the user can actually see and correct what
    # was extracted, rather than it silently never appearing.
    if case_file.floor_wise_area:
        lines.append(f"- floor_wise_area: {_format_floor_wise_area(case_file.floor_wise_area)}")
    if case_file.kitchen_count is not None:
        lines.append(f"- kitchen_count: {case_file.kitchen_count}")
    if case_file.door_count is not None:
        lines.append(f"- door_count: {case_file.door_count}")
    lines.append("\nIs this all correct, or is anything off?")
    return "\n".join(lines)


def start_conversation(case_file: CaseFile) -> TurnResult:
    prompt = (
        _confirmation_summary(case_file)
        if _all_intake_fields_complete(case_file)
        else _next_step_message(case_file)
    )
    return TurnResult(case_file=case_file, agent_message=OPENING_PROMPT + prompt)


def _safe_answer_question(llm: LLMClient, question: str, case_file: CaseFile) -> str:
    """Wraps llm.answer_question with the same fail-open behavior every other
    LLM call in this module has. Both call sites below were, until a live
    browser test caught it, missing this - Knowledge Q&A with no LLM
    configured surfaced as an uncaught 500 instead of a graceful message.

    Passing case_file through to build_qa_context() fixes a second live-
    tested bug: without it, the Q&A side-branch only ever saw static
    code-book material, so a question about a just-uploaded document was
    answered as if nothing had been uploaded at all, even though the case
    file already had the extracted facts.
    """
    try:
        return llm.answer_question(question, build_qa_context(question, case_file=case_file))
    except LLMUnavailableError:
        # Checked before the LLMNotConfiguredError branch below since it's a
        # subclass - a live deployment hit this exact case (Groq's free
        # tier's per-minute output-token quota exhausted by a few document
        # uploads in a row) and deserves a different message than "no key
        # configured", which would be actively misleading here.
        return (
            "The AI provider is temporarily rate-limited or unavailable - "
            "please try again in a minute. The building-detail questions "
            "still work without one."
        )
    except LLMNotConfiguredError:
        return (
            "I can't answer general questions right now - no LLM provider is "
            "configured for this deployment. The building-detail questions "
            "still work without one."
        )


def handle_turn(case_file: CaseFile, user_message: str, llm: LLMClient) -> TurnResult:
    if case_file.conversation_stage == ConversationStage.CLASSIFIED:
        answer = _safe_answer_question(llm, user_message, case_file)
        return TurnResult(case_file=case_file, agent_message=answer)

    if case_file.conversation_stage == ConversationStage.CONFIRMING:
        try:
            extracted = llm.extract_fields(
                user_message,
                _ALL_FIELD_TYPES,
                context="The user is confirming or correcting a summary of their building's details.",
            )
        except LLMNotConfiguredError:
            extracted = {}
        case_file = _apply_extracted_fields(case_file, extracted)
        case_file.classification_result = classify(case_file)
        case_file.conversation_stage = ConversationStage.CLASSIFIED
        case_file.updated_at = datetime.now(timezone.utc)
        result = case_file.classification_result
        summary = (
            f"Thanks — classified. Applies to NBCS Part F: {result.applies}. "
            f"Table 7 reference: {result.table_7_ref or 'N/A'}."
            + (" ⚠ This occupancy requires mandatory human/expert review." if result.require_human_review_flag else "")
            + "\n\nFull report:\n\n"
            + generate_report_markdown(case_file)
        )
        return TurnResult(case_file=case_file, agent_message=summary)

    # INTAKE stage
    subdivision_index = _missing_subdivision_index(case_file)
    if subdivision_index is not None:
        return _handle_mixed_use_subdivision_turn(case_file, user_message, llm, subdivision_index)

    node = next_node(case_file)
    if node is None:
        case_file.conversation_stage = ConversationStage.CONFIRMING
        return TurnResult(case_file=case_file, agent_message=_confirmation_summary(case_file))

    pending_question = node.prompt(case_file)

    rate_limited = False
    try:
        intent = llm.classify_intent(user_message, pending_question)
    except LLMUnavailableError:
        intent = "answer"  # fail open to the deterministic spine when temporarily unavailable
        rate_limited = True
    except LLMNotConfiguredError:
        intent = "answer"  # fail open to the deterministic spine when no LLM is configured

    if intent == "question":
        answer = _safe_answer_question(llm, user_message, case_file)
        return TurnResult(
            case_file=case_file,
            agent_message=f"{answer}\n\n(Back to: {pending_question})",
        )

    try:
        extracted = llm.extract_fields(
            user_message, _field_types_for(node, case_file), context=node.context
        )
    except LLMUnavailableError:
        extracted = {}
        rate_limited = True
    except LLMNotConfiguredError:
        extracted = {}

    case_file = _apply_extracted_fields(case_file, extracted)

    nudge = ""
    if node.id == "goal" and case_file.goal in _GOAL_UPLOAD_NUDGES:
        nudge += _GOAL_UPLOAD_NUDGES[case_file.goal]
    if node.id in ("height", "area") and residential_self_cert_eligible(case_file):
        nudge += RESIDENTIAL_SELF_CERT_NUDGE

    if _all_intake_fields_complete(case_file):
        case_file.conversation_stage = ConversationStage.CONFIRMING
        return TurnResult(
            case_file=case_file, agent_message=nudge + _confirmation_summary(case_file)
        )

    if not extracted:
        # Nothing usable was extracted - re-ask the same question rather than
        # silently advancing on an empty/unparseable answer. Distinguish a
        # transient provider failure (try again shortly, your answer was
        # fine) from a genuinely unparseable answer, so a user mid-upload-
        # flurry rate limit isn't told their perfectly clear answer "didn't
        # catch" when the real cause was the AI provider being busy.
        if rate_limited:
            return TurnResult(
                case_file=case_file,
                agent_message=(
                    "The AI provider is temporarily rate-limited or unavailable - "
                    f"please try again in a minute. {pending_question}"
                ),
            )
        return TurnResult(
            case_file=case_file,
            agent_message=f"Sorry, I didn't catch that. {pending_question}",
        )

    return TurnResult(case_file=case_file, agent_message=nudge + _next_step_message(case_file))


def _handle_mixed_use_subdivision_turn(
    case_file: CaseFile, user_message: str, llm: LLMClient, index: int
) -> TurnResult:
    """Node 3c's own mini turn-handler - same shape as the regular node path
    in handle_turn (Q&A side-branch, fail-open on rate limit/no LLM, re-ask
    on an unparseable answer), but applies its result to one specific
    occupancy_breakdown item's subdivision instead of a top-level field.
    """
    item = case_file.occupancy_breakdown[index]
    pending_question = _mixed_use_subdivision_prompt(item)

    rate_limited = False
    try:
        intent = llm.classify_intent(user_message, pending_question)
    except LLMUnavailableError:
        intent = "answer"
        rate_limited = True
    except LLMNotConfiguredError:
        intent = "answer"

    if intent == "question":
        answer = _safe_answer_question(llm, user_message, case_file)
        return TurnResult(
            case_file=case_file, agent_message=f"{answer}\n\n(Back to: {pending_question})"
        )

    try:
        extracted = llm.extract_fields(
            user_message,
            _mixed_use_subdivision_field_types(item),
            context=(
                f"The user is describing the {item.type.value} component "
                f"({item.floor_range}) of a Mixed Use building."
            ),
        )
    except LLMUnavailableError:
        extracted = {}
        rate_limited = True
    except LLMNotConfiguredError:
        extracted = {}

    subdivision = extracted.get("occupancy_subdivision")
    if not subdivision:
        if rate_limited:
            return TurnResult(
                case_file=case_file,
                agent_message=(
                    "The AI provider is temporarily rate-limited or unavailable - "
                    f"please try again in a minute. {pending_question}"
                ),
            )
        return TurnResult(
            case_file=case_file, agent_message=f"Sorry, I didn't catch that. {pending_question}"
        )

    case_file = _apply_mixed_use_subdivision(case_file, index, subdivision)

    if _all_intake_fields_complete(case_file):
        case_file.conversation_stage = ConversationStage.CONFIRMING
        return TurnResult(case_file=case_file, agent_message=_confirmation_summary(case_file))

    return TurnResult(case_file=case_file, agent_message=_next_step_message(case_file))
