"""Case File API - product scope section B.3 (Dialogue Manager surface).

Two layers live here: a thin CRUD + classify + report surface over the Case
File (usable with no LLM at all - see the earlier commit), and a
conversational surface (/start, /message) that drives app/dialogue/manager.py.
The conversational endpoints need ANTHROPIC_API_KEY configured in the
deployment environment; without it they still work for the deterministic
parts of the intake (the dialogue manager fails open to "treat this as an
answer" per manager.py) but Knowledge Q&A and free-text field extraction
degrade to "message not understood, please rephrase".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app import message_store
from app.auth.dependencies import get_current_user_optional
from app.dialogue.manager import handle_turn, start_conversation
from app.engine.classifier import classify
from app.ingest.apply import ingest_document
from app.llm.client import LLMClient
from app.models.case_file import CaseFile, ConversationStage
from app.models.conversation import ConversationMessage, MessageKind, MessageRole
from app.models.user import User
from app.reports.exporters import render_docx, render_pdf, safe_report_filename
from app.reports.generator import generate_report_markdown
from app.store import get as store_get
from app.store import save as store_save

# Matches app/ingest/pipeline.py's supported content types - kept here too
# so a bad upload is rejected with a clear 415 before any file processing,
# rather than reaching the pipeline's own (also-safe) unsupported-type path.
_SUPPORTED_UPLOAD_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB - generous for a scanned plan/letter, not unbounded

router = APIRouter(prefix="/case-files", tags=["case-files"])


def get_llm_client() -> LLMClient:
    """FastAPI dependency - overridden with a fake in tests so the endpoint
    never needs real Anthropic credentials or network access to be tested.
    """
    return LLMClient()


def _check_access(case_file: CaseFile, current_user: User | None) -> None:
    """Phase 2 (accounts): a case file with no owner is an anonymous, Phase
    1-style case file - open to anyone who knows its session_id, exactly
    Phase 1's original (unauthenticated) model, so nothing that already
    depends on that behavior breaks. A case file WITH an owner is only
    accessible to that account - every other endpoint below calls this
    immediately after fetching the case file, before doing anything else
    with it.
    """
    if case_file.owner_user_id is None:
        return
    if current_user is None or current_user.id != case_file.owner_user_id:
        raise HTTPException(status_code=403, detail="You do not have access to this case file")


@router.post("", response_model=CaseFile, status_code=201)
def create_case_file(
    case_file: CaseFile | None = None,
    current_user: User | None = Depends(get_current_user_optional),
) -> CaseFile:
    if case_file is None:
        case_file = CaseFile(session_id=str(uuid.uuid4()))
    elif not case_file.session_id:
        case_file.session_id = str(uuid.uuid4())
    # A logged-in caller's case files belong to their account from the
    # start; an anonymous caller gets Phase 1's original behavior
    # (owner_user_id stays None, open to anyone with the session_id).
    if current_user is not None:
        case_file.owner_user_id = current_user.id
    return store_save(case_file)


# NOTE: declared before the "/{session_id}" route below on purpose - FastAPI
# matches routes in declaration order, so a literal path that could also be
# read as a session id has to come first.
@router.get("/opening-message")
def get_opening_message() -> dict:
    """The greeting + first intake question for a not-yet-created case file.

    Exists so the Overview page can show the assistant's opening message
    immediately WITHOUT creating (and therefore persisting) a case file.
    Before this, merely opening the Overview page created a project - so
    navigating away and back repeatedly littered Project History with
    empty projects the user never actually started. A case file is now
    only created once there's something real to record: a typed answer or
    an uploaded document. Persists nothing; `start_conversation` here runs
    against a throwaway in-memory CaseFile purely to render the prompt.
    """
    draft = CaseFile(session_id="")
    return {"agent_message": start_conversation(draft).agent_message}


@router.get("/{session_id}", response_model=CaseFile)
def get_case_file(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> CaseFile:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    return case_file


@router.put("/{session_id}", response_model=CaseFile)
def update_case_file(
    session_id: str, updates: dict, current_user: User | None = Depends(get_current_user_optional)
) -> CaseFile:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    # owner_user_id can only be set at creation (create_case_file) - never
    # let a PUT body reassign ownership, whether by accident or by a
    # malicious client trying to transfer/plant a case file onto another
    # account.
    updates.pop("owner_user_id", None)
    # model_copy(update=...) would set raw dict values without re-validating/
    # coercing them (e.g. a plain "Storage" string would never become the
    # OccupancyType enum member) - round-trip through model_validate instead
    # so every field goes through Pydantic's normal type coercion.
    merged = {**case_file.model_dump(), **updates}
    updated = CaseFile.model_validate(merged)
    updated.updated_at = datetime.now(timezone.utc)
    return store_save(updated)


@router.post("/{session_id}/classify", response_model=CaseFile)
def classify_case_file(
    session_id: str, current_user: User | None = Depends(get_current_user_optional)
) -> CaseFile:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    case_file.classification_result = classify(case_file)
    case_file.conversation_stage = ConversationStage.CLASSIFIED
    case_file.updated_at = datetime.now(timezone.utc)
    return store_save(case_file)


@router.post("/{session_id}/what-if", response_model=CaseFile)
def what_if_case_file(
    session_id: str, updates: dict, current_user: User | None = Depends(get_current_user_optional)
) -> CaseFile:
    """Phase 2: "what if this field were X" - reclassifies a hypothetical
    copy of the case file so the UI can show the resulting classification/
    compliance without ever touching the real one. Same merge-and-
    revalidate `update_case_file` above uses, then the same `classify()`
    real classification uses - deliberately no separate what-if business
    logic to keep in sync with the real rules - but this never calls
    store_save(), so the persisted case file (and its conversation_stage)
    is completely unaffected by exploring a scenario.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    updates.pop("owner_user_id", None)
    merged = {**case_file.model_dump(), **updates}
    hypothetical = CaseFile.model_validate(merged)
    hypothetical.classification_result = classify(hypothetical)
    return hypothetical


@router.get("/{session_id}/report")
def get_report(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> dict:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    return {"markdown": generate_report_markdown(case_file)}


@router.get("/{session_id}/report.pdf")
def get_report_pdf(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> Response:
    """Phase 2: a real PDF of the same report /report already returns as
    markdown - never a second source of truth for report content, see
    app/reports/exporters.py.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    filename = safe_report_filename(case_file)
    return Response(
        content=render_pdf(case_file),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


@router.get("/{session_id}/report.docx")
def get_report_docx(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> Response:
    """Phase 2: a real DOCX counterpart to /report.pdf above."""
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    filename = safe_report_filename(case_file)
    return Response(
        content=render_docx(case_file),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'},
    )


@router.post("/{session_id}/start")
def start(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> dict:
    """Returns the opening question (product scope B.5, Node 0/1) without
    consuming a user message - call this once right after creating a case
    file to get the first prompt to show the user.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    result = start_conversation(case_file)
    store_save(result.case_file)
    message_store.append(session_id, MessageRole.AGENT, result.agent_message)
    return {"agent_message": result.agent_message, "case_file": result.case_file}


@router.get("/{session_id}/messages", response_model=list[ConversationMessage])
def get_messages(
    session_id: str,
    limit: int = Query(default=message_store.DEFAULT_PAGE_SIZE, ge=1, le=message_store.MAX_PAGE_SIZE),
    before_id: int | None = Query(default=None),
    current_user: User | None = Depends(get_current_user_optional),
) -> list[ConversationMessage]:
    """The persisted chat transcript, oldest-first - what the Overview page
    reloads so leaving the page (or reopening the project later from
    Project History) doesn't lose the conversation. Returns the most recent
    `limit` messages; page further back with `before_id` (the id of the
    oldest message already held).
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    return message_store.list_for_session(session_id, limit=limit, before_id=before_id)


@router.post("/{session_id}/message")
def send_message(
    session_id: str,
    body: dict,
    llm: LLMClient = Depends(get_llm_client),
    current_user: User | None = Depends(get_current_user_optional),
) -> dict:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    user_message = body.get("message")
    if not user_message:
        raise HTTPException(status_code=422, detail="'message' is required")

    previous_stage = case_file.conversation_stage
    result = handle_turn(case_file, user_message, llm)
    store_save(result.case_file)

    message_store.append(session_id, MessageRole.USER, user_message)
    message_store.append(session_id, MessageRole.AGENT, result.agent_message)
    # The moment a case file becomes classified is recorded as its own
    # structured message so a reloaded transcript still shows the
    # classification card, rather than the frontend having to re-derive
    # "this turn is where it got classified" from a stage it can no longer
    # see the history of.
    if (
        previous_stage != ConversationStage.CLASSIFIED
        and result.case_file.conversation_stage == ConversationStage.CLASSIFIED
    ):
        message_store.append(
            session_id,
            MessageRole.AGENT,
            kind=MessageKind.CLASSIFICATION_RESULT,
            payload=result.case_file.classification_result.model_dump(mode="json"),
        )

    return {"agent_message": result.agent_message, "case_file": result.case_file}


@router.post("/{session_id}/documents")
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    llm: LLMClient = Depends(get_llm_client),
    current_user: User | None = Depends(get_current_user_optional),
) -> dict:
    """Product scope §B.7 - runs the tiered OCR/vision pipeline on an
    uploaded PDF/PNG/JPEG, extracts whatever Case File facts it can, and
    merges them in as document-sourced (never higher-confidence than a
    user's own chat answer - see app/ingest/apply.py). Every field this
    finds still needs the same B.5 Node 8 confirmation as any other
    document-sourced fact before a report is generated - this endpoint pre-
    fills, it never finalizes.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)

    if file.content_type not in _SUPPORTED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Upload a PDF, PNG, or JPEG.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (20 MB limit).")

    filename = file.filename or "upload"
    updated_case_file, summary = ingest_document(
        case_file, file_bytes, file.content_type, filename, llm
    )
    store_save(updated_case_file)
    # Recorded as a structured message (not prose) so a reloaded transcript
    # re-renders the same extraction-result card the user saw live.
    message_store.append(
        session_id,
        MessageRole.AGENT,
        kind=MessageKind.DOCUMENT_RESULT,
        payload={"file_name": filename, "summary": asdict(summary)},
    )
    return {"summary": asdict(summary), "case_file": updated_case_file}
