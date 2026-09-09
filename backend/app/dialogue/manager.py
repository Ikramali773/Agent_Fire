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

Node 2a (the renewal-upload nudge) and Node 3a (the residential early-exit
shortcut) are both handled here rather than as dialogue/nodes.py Nodes: each
is a one-off message appended around an existing node transition, not a
field to collect - the actual "skip egress/existing_systems" logic for Node
3a lives in those nodes' own `applicable` callbacks
(residential_self_cert_eligible in dialogue/nodes.py). Deliberately still
deferred (see backend/README.md): the Node 0 document-upload branch
proactively offering itself as a step for every goal (not just renewal).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.dialogue.nodes import NODES, SUBDIVISION_OPTIONS, next_node, residential_self_cert_eligible
from app.engine.classifier import classify
from app.knowledge.context import build_qa_context
from app.llm.client import LLMClient, LLMNotConfiguredError
from app.models.case_file import CaseFile, ConversationStage, FieldSource, FieldSourceKind, Goal
from app.reports.generator import generate_report_markdown

OPENING_PROMPT = (
    "Hi — I can help you understand fire-safety requirements and NOC "
    "readiness for your building under NBCS 2026 Part F. Let's go through "
    "your building's details to see what applies to you. You can also ask "
    "me a general question at any point.\n\n"
)

# Node 2a, product scope §B.5: when the user says they're renewing an
# existing NOC, proactively point them at the upload widget (reuses the
# already-built OCR ingest pipeline, §B.7) instead of only supporting it as
# a passive button they have to notice on their own.
RENEWAL_UPLOAD_NUDGE = (
    "Since you're renewing an existing NOC, you can upload your existing NOC "
    "certificate or approved plan now (the 📎 attach button below) and I'll "
    "pull in whatever details it has — or just keep answering by hand.\n\n"
)

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

_ALL_FIELD_TYPES = {name: typ for node in NODES for name, typ in node.field_types.items()}


@dataclass
class TurnResult:
    case_file: CaseFile
    agent_message: str


def _field_types_for(node, case_file: CaseFile) -> dict[str, type]:
    if node.id == "subdivision":
        from typing import Literal

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
    lines.append("\nIs this all correct, or is anything off?")
    return "\n".join(lines)


def start_conversation(case_file: CaseFile) -> TurnResult:
    node = next_node(case_file)
    prompt = node.prompt(case_file) if node else _confirmation_summary(case_file)
    return TurnResult(case_file=case_file, agent_message=OPENING_PROMPT + prompt)


def _safe_answer_question(llm: LLMClient, question: str) -> str:
    """Wraps llm.answer_question with the same fail-open behavior every other
    LLM call in this module has. Both call sites below were, until a live
    browser test caught it, missing this - Knowledge Q&A with no LLM
    configured surfaced as an uncaught 500 instead of a graceful message.
    """
    try:
        return llm.answer_question(question, build_qa_context(question))
    except LLMNotConfiguredError:
        return (
            "I can't answer general questions right now - no LLM provider is "
            "configured for this deployment. The building-detail questions "
            "still work without one."
        )


def handle_turn(case_file: CaseFile, user_message: str, llm: LLMClient) -> TurnResult:
    if case_file.conversation_stage == ConversationStage.CLASSIFIED:
        answer = _safe_answer_question(llm, user_message)
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
    node = next_node(case_file)
    if node is None:
        case_file.conversation_stage = ConversationStage.CONFIRMING
        return TurnResult(case_file=case_file, agent_message=_confirmation_summary(case_file))

    pending_question = node.prompt(case_file)

    try:
        intent = llm.classify_intent(user_message, pending_question)
    except LLMNotConfiguredError:
        intent = "answer"  # fail open to the deterministic spine when no LLM is configured

    if intent == "question":
        answer = _safe_answer_question(llm, user_message)
        return TurnResult(
            case_file=case_file,
            agent_message=f"{answer}\n\n(Back to: {pending_question})",
        )

    try:
        extracted = llm.extract_fields(
            user_message, _field_types_for(node, case_file), context=node.context
        )
    except LLMNotConfiguredError:
        extracted = {}

    case_file = _apply_extracted_fields(case_file, extracted)

    nudge = ""
    if node.id == "goal" and case_file.goal == Goal.RENEW_NOC:
        nudge += RENEWAL_UPLOAD_NUDGE
    if node.id in ("height", "area") and residential_self_cert_eligible(case_file):
        nudge += RESIDENTIAL_SELF_CERT_NUDGE

    next_pending = next_node(case_file)
    if next_pending is None:
        case_file.conversation_stage = ConversationStage.CONFIRMING
        return TurnResult(
            case_file=case_file, agent_message=nudge + _confirmation_summary(case_file)
        )

    if not extracted:
        # Nothing usable was extracted - re-ask the same question rather than
        # silently advancing on an empty/unparseable answer.
        return TurnResult(
            case_file=case_file,
            agent_message=f"Sorry, I didn't catch that. {pending_question}",
        )

    return TurnResult(case_file=case_file, agent_message=nudge + next_pending.prompt(case_file))
