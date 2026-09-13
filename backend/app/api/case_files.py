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
from enum import Enum

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app import change_log, grant_store, message_store, review_store
from app.auth.dependencies import get_current_user_optional, get_current_user_required
from app.auth.user_store import get_user_by_email
from app.dialogue.manager import handle_turn, start_conversation
from app.engine.classifier import classify
from app.ingest.apply import ingest_document
from app.llm.client import LLMClient
from app.models.case_file import CaseFile, ConversationStage, FieldSource, FieldSourceKind
from app.models.change_log import ChangeSource, FieldChange
from app.models.grant import CaseFileGrant
from app.models.review import RECORDABLE_STATUSES, ReviewState, ReviewStatus
from app.models.conversation import ConversationMessage, MessageKind, MessageRole
from app.models.user import User
from app.reports.exporters import render_docx, render_pdf, safe_report_filename
from app.reports.generator import generate_report_markdown
from app.reports.handoff import generate_handoff_markdown
from app.store import delete as store_delete
from app.store import get as store_get
from app.store import save as store_save

# Matches app/ingest/pipeline.py's supported content types - kept here too
# so a bad upload is rejected with a clear 415 before any file processing,
# rather than reaching the pipeline's own (also-safe) unsupported-type path.
_SUPPORTED_UPLOAD_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}

# Fields a direct edit must NOT stamp provenance for: bookkeeping, plus the
# two things the system derives rather than the user asserting
# (classification_result, conversation_stage) and the record of what was
# uploaded (source_documents).
_PROVENANCE_EXEMPT_FIELDS = frozenset(
    {
        "session_id",
        "owner_user_id",
        "created_at",
        "updated_at",
        "field_sources",
        "classification_result",
        "conversation_stage",
        "source_documents",
    }
)
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB - generous for a scanned plan/letter, not unbounded

router = APIRouter(prefix="/case-files", tags=["case-files"])


def get_llm_client() -> LLMClient:
    """FastAPI dependency - overridden with a fake in tests so the endpoint
    never needs real Anthropic credentials or network access to be tested.
    """
    return LLMClient()


class Access(str, Enum):
    """What a request needs to be allowed to do.

    Phase 2 had one level: you own it or you don't. Phase 3 adds reviewers,
    who must be able to read a project and judge it WITHOUT being able to
    change it - a verdict on facts the reviewer could have edited is worth
    nothing. So the question is no longer "do you have access" but "access
    to do what".
    """

    READ = "read"
    """View the case file, its transcript, its history, its report - and
    record a review verdict, which is the one thing a reviewer adds."""

    WRITE = "write"
    """Change the facts: edit fields, continue the conversation, upload a
    document, run the classifier. Owner only."""

    OWN = "own"
    """Administer the project: delete it, share it, revoke a share. Owner
    only - a reviewer must never be able to re-share someone else's
    project onward."""


def _check_access(
    case_file: CaseFile, current_user: User | None, need: Access = Access.READ
) -> None:
    """Phase 2 (accounts) + Phase 3 (sharing).

    A case file with no owner is an anonymous, Phase 1-style case file -
    open to anyone who knows its session_id, exactly Phase 1's original
    (unauthenticated) model, so nothing that already depends on that
    behavior breaks. Note this is unchanged by Phase 3: an anonymous case
    file has no owner to share it, and nothing to share it with.

    A case file WITH an owner is the owner's for everything. A reviewer it
    has been shared with gets READ only: they can see it and record a
    verdict, and every WRITE or OWN request from them is a 403, same as
    from a stranger. Every endpoint below calls this immediately after
    fetching the case file, before doing anything else with it.
    """
    if case_file.owner_user_id is None:
        return
    if current_user is None:
        raise HTTPException(status_code=403, detail="You do not have access to this case file")
    if current_user.id == case_file.owner_user_id:
        return
    if need is Access.READ and grant_store.has_grant(case_file.session_id, current_user.id):
        return
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
    _check_access(case_file, current_user, Access.WRITE)
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
    # A directly-edited field is user-confirmed, and must say so. The
    # dialogue path (dialogue/manager.py) and the ingest path
    # (ingest/apply.py) have always recorded provenance; this one never
    # did, so a field typed into the Case File page showed up with no
    # source at all - including in the Phase 3 handoff pack, whose entire
    # purpose is telling a reviewer where each number came from.
    # Read back off `updated` rather than the raw request body so the
    # recorded value is the coerced one Pydantic actually stored.
    for field_name in updates:
        if field_name in _PROVENANCE_EXEMPT_FIELDS or not hasattr(updated, field_name):
            continue
        updated.field_sources[field_name] = FieldSource(
            value=getattr(updated, field_name), source=FieldSourceKind.USER, confidence=1.0
        )
    updated.updated_at = datetime.now(timezone.utc)
    saved = store_save(updated)
    change_log.record(
        case_file, saved, ChangeSource.USER, actor_user_id=current_user.id if current_user else None
    )
    return saved


@router.delete("/{session_id}", status_code=204)
def delete_case_file(
    session_id: str, current_user: User | None = Depends(get_current_user_optional)
) -> Response:
    """Deletes a project and everything attached to it: the case file, its
    chat transcript, its change log, its review history and every share.

    All of it, explicitly - a user deleting a project expects their
    conversation and its history to go with it, not to be left behind in
    the database, and a share left behind would put a dead row in a
    reviewer's queue. Irreversible; there is no soft-delete/undo, so the UI
    confirms first.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user, Access.OWN)
    message_store.delete_for_session(session_id)
    change_log.delete_for_session(session_id)
    review_store.delete_for_session(session_id)
    grant_store.delete_for_session(session_id)
    store_delete(session_id)
    return Response(status_code=204)


@router.post("/{session_id}/claim", response_model=CaseFile)
def claim_case_file(
    session_id: str, current_user: User = Depends(get_current_user_required)
) -> CaseFile:
    """Attaches an anonymous case file to the calling account.

    Closes a real gap in Phase 2's account model: `owner_user_id` was only
    ever set at creation time, so a project someone started before signing
    in stayed anonymous forever - invisible in Project History and in the
    chat rail, even to the person who had just created it in that same
    browser. Claiming is the one operation that may set an owner after the
    fact.

    Only an UNOWNED case file can be claimed. Claiming one you already own
    is a no-op (idempotent, so a retry or React's double-invoked effect is
    harmless); claiming someone else's is a 403, exactly like every other
    access to it - this must never become a way to take over a project by
    guessing a session id.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    if case_file.owner_user_id == current_user.id:
        return case_file
    if case_file.owner_user_id is not None:
        raise HTTPException(status_code=403, detail="You do not have access to this case file")
    case_file.owner_user_id = current_user.id
    case_file.updated_at = datetime.now(timezone.utc)
    return store_save(case_file)


def _build_review_state(case_file: CaseFile, current_user: User | None) -> ReviewState:
    """One response with everything the Review page needs for a case."""
    can_record = case_file.owner_user_id is None or (
        current_user is not None
        and (
            current_user.id == case_file.owner_user_id
            or grant_store.has_grant(case_file.session_id, current_user.id)
        )
    )
    return ReviewState(
        session_id=case_file.session_id,
        project_name=case_file.project_name,
        requires_review=case_file.classification_result.require_human_review_flag,
        reasons=case_file.classification_result.review_reasons,
        status=review_store.current_status(case_file.session_id),
        events=review_store.list_for_session(case_file.session_id),
        flagged_at=case_file.updated_at,
        can_record_verdict=can_record,
    )


@router.get("/{session_id}/review", response_model=ReviewState)
def get_review(
    session_id: str, current_user: User | None = Depends(get_current_user_optional)
) -> ReviewState:
    """The review state of one case: why it was flagged, where it stands,
    and everything anyone has recorded about it.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    return _build_review_state(case_file, current_user)


@router.post("/{session_id}/review", response_model=ReviewState, status_code=201)
def record_review(
    session_id: str, body: dict, current_user: User | None = Depends(get_current_user_optional)
) -> ReviewState:
    """Records a reviewer's verdict.

    READ access, deliberately: recording a verdict is precisely what a
    shared-with reviewer is here to do, and it changes nothing about the
    case file itself.

    It NEVER rewrites the classification. That is the whole architecture of
    this feature, not an implementation detail - product scope Part G
    Principle 1 is "LLM reasons and explains; deterministic engines
    decide", and letting a person hand-edit the engine's verdict breaks it
    exactly as surely as letting the LLM do it. A reviewer who believes the
    output is wrong changes the FACTS (PUT /case-files/{id}, which they can
    only do if they own it) and the engine reclassifies from those. Their
    opinion is recorded alongside the classification, never on top of it.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)

    raw_status = (body.get("status") or "").strip()
    try:
        status = ReviewStatus(raw_status)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"'status' must be one of: {', '.join(sorted(s.value for s in RECORDABLE_STATUSES))}",
        )
    if status not in RECORDABLE_STATUSES:
        # needs_review is derived from "no events yet", so accepting it as
        # a verdict would let a review be silently rewound and make the
        # history lie about what happened.
        raise HTTPException(
            status_code=422,
            detail=f"'{status.value}' is the starting state, not a verdict that can be recorded",
        )

    review_store.record(
        session_id,
        status,
        note=(body.get("note") or "").strip(),
        actor_user_id=current_user.id if current_user else None,
        actor_email=current_user.email if current_user else None,
    )
    return _build_review_state(store_get(session_id), current_user)


@router.get("/{session_id}/shares", response_model=list[CaseFileGrant])
def list_shares(
    session_id: str, current_user: User | None = Depends(get_current_user_optional)
) -> list[CaseFileGrant]:
    """Who this project is shared with. READ, so a reviewer can see who
    else is looking at the same case - useful, and not sensitive to anyone
    who can already read the project.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    return grant_store.list_for_session(session_id)


@router.post("/{session_id}/shares", response_model=CaseFileGrant, status_code=201)
def create_share(
    session_id: str, body: dict, current_user: User | None = Depends(get_current_user_optional)
) -> CaseFileGrant:
    """Shares a project with a reviewer, by the email of their account.

    OWN, not WRITE: a reviewer must never be able to pass someone else's
    project onward. Requires the recipient to already have an account -
    inviting an address that has never signed up would mean sending mail,
    which this product does not do, and silently creating an account for
    someone is worse than an honest 404.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user, Access.OWN)
    if current_user is None:
        # An anonymous case file has no owner to share it and nobody to
        # share it as - claim it first (POST /{id}/claim).
        raise HTTPException(
            status_code=401, detail="Sign in and claim this project before sharing it"
        )

    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="'email' is required")
    if email == current_user.email.lower():
        raise HTTPException(status_code=422, detail="You already own this project")

    reviewer = get_user_by_email(email)
    if reviewer is None:
        raise HTTPException(
            status_code=404, detail=f"No account found for {email}. They need to sign up first."
        )
    return grant_store.grant(
        session_id,
        granted_to_user_id=reviewer.id,
        granted_to_email=reviewer.email,
        granted_by_user_id=current_user.id,
    )


@router.delete("/{session_id}/shares/{granted_to_user_id}", status_code=204)
def revoke_share(
    session_id: str,
    granted_to_user_id: str,
    current_user: User | None = Depends(get_current_user_optional),
) -> Response:
    """Revokes a share. Immediate - the reviewer's next request is a 403.

    Their already-recorded verdicts stay: a review that happened, happened,
    and deleting the record of it because access was withdrawn would make
    the history lie.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user, Access.OWN)
    if not grant_store.revoke(session_id, granted_to_user_id):
        raise HTTPException(status_code=404, detail="This project is not shared with that account")
    return Response(status_code=204)


@router.post("/{session_id}/classify", response_model=CaseFile)
def classify_case_file(
    session_id: str, current_user: User | None = Depends(get_current_user_optional)
) -> CaseFile:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user, Access.WRITE)
    before = case_file.model_copy(deep=True)
    case_file.classification_result = classify(case_file)
    case_file.conversation_stage = ConversationStage.CLASSIFIED
    case_file.updated_at = datetime.now(timezone.utc)
    saved = store_save(case_file)
    # Only the stage transition is logged, not the classification result
    # itself - that is already stored in full as a structured transcript
    # message (see app/models/change_log.py).
    change_log.record(
        before, saved, ChangeSource.SYSTEM, actor_user_id=current_user.id if current_user else None
    )
    return saved


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
        content=render_pdf(generate_report_markdown(case_file)),
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
        content=render_docx(generate_report_markdown(case_file)),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'},
    )


def _handoff_markdown(case_file: CaseFile, current_user: User | None) -> str:
    return generate_handoff_markdown(
        case_file,
        _build_review_state(case_file, current_user),
        change_log.list_for_session(case_file.session_id, limit=change_log.MAX_PAGE_SIZE),
    )


@router.get("/{session_id}/handoff")
def get_handoff(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> dict:
    """Phase 3: the consultant handoff pack as markdown - the report, plus
    why review is required, where every fact came from, and what has
    changed. See app/reports/handoff.py for why those three.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    return {"markdown": _handoff_markdown(case_file, current_user)}


@router.get("/{session_id}/handoff.pdf")
def get_handoff_pdf(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> Response:
    """The handoff pack as a PDF, through the same renderer as the report."""
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    filename = safe_report_filename(case_file)
    return Response(
        content=render_pdf(_handoff_markdown(case_file, current_user)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename} - reviewer handoff.pdf"'},
    )


@router.get("/{session_id}/handoff.docx")
def get_handoff_docx(session_id: str, current_user: User | None = Depends(get_current_user_optional)) -> Response:
    """The handoff pack as a DOCX, so a consultant can annotate it."""
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    filename = safe_report_filename(case_file)
    return Response(
        content=render_docx(_handoff_markdown(case_file, current_user)),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename} - reviewer handoff.docx"'},
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
    _check_access(case_file, current_user, Access.WRITE)
    before = case_file.model_copy(deep=True)
    result = start_conversation(case_file)
    store_save(result.case_file)
    change_log.record(
        before, result.case_file, ChangeSource.SYSTEM, actor_user_id=current_user.id if current_user else None
    )
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


@router.get("/{session_id}/changes", response_model=list[FieldChange])
def get_changes(
    session_id: str,
    limit: int = Query(default=change_log.DEFAULT_PAGE_SIZE, ge=1, le=change_log.MAX_PAGE_SIZE),
    before_id: int | None = Query(default=None),
    current_user: User | None = Depends(get_current_user_optional),
) -> list[FieldChange]:
    """The per-field change log for one case file, NEWEST first.

    The answer to "this building was 24 m yesterday and 68 m today - who
    changed it, and off the back of what?", which Project History (a
    project list showing only current state) could never give. Returns the
    most recent `limit` changes; page further back with `before_id`.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    _check_access(case_file, current_user)
    return change_log.list_for_session(session_id, limit=limit, before_id=before_id)


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
    _check_access(case_file, current_user, Access.WRITE)
    user_message = body.get("message")
    if not user_message:
        raise HTTPException(status_code=422, detail="'message' is required")

    previous_stage = case_file.conversation_stage
    # handle_turn mutates the case file in place, so this has to be a deep
    # copy - keeping a reference would compare the result against itself
    # and log nothing.
    before = case_file.model_copy(deep=True)
    result = handle_turn(case_file, user_message, llm)
    store_save(result.case_file)
    change_log.record(
        before, result.case_file, ChangeSource.DIALOGUE, actor_user_id=current_user.id if current_user else None
    )

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
    _check_access(case_file, current_user, Access.WRITE)

    if file.content_type not in _SUPPORTED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Upload a PDF, PNG, or JPEG.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (20 MB limit).")

    filename = file.filename or "upload"
    # Same reason as /message: ingest_document merges into the case file
    # it is given, so the "before" has to be a copy.
    before = case_file.model_copy(deep=True)
    updated_case_file, summary = ingest_document(
        case_file, file_bytes, file.content_type, filename, llm
    )
    store_save(updated_case_file)
    change_log.record(
        before, updated_case_file, ChangeSource.DOCUMENT, actor_user_id=current_user.id if current_user else None
    )
    # Recorded as a structured message (not prose) so a reloaded transcript
    # re-renders the same extraction-result card the user saw live.
    message_store.append(
        session_id,
        MessageRole.AGENT,
        kind=MessageKind.DOCUMENT_RESULT,
        payload={"file_name": filename, "summary": asdict(summary)},
    )
    return {"summary": asdict(summary), "case_file": updated_case_file}
