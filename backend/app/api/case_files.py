"""Case File API - product scope section B.3 (Dialogue Manager surface).

This is a thin CRUD + classify + report surface over the Case File. It does
NOT implement the guided question-tree conversation (B.5) or the LLM-driven
dialogue manager - those need an LLM provider decision first (see the repo
README/TODO). What's here is enough to build/test the deterministic engine
and report generator end-to-end, and gives the eventual dialogue manager a
concrete API to call into.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.engine.classifier import classify
from app.models.case_file import CaseFile, ConversationStage
from app.reports.generator import generate_report_markdown
from app.store import get as store_get
from app.store import save as store_save

router = APIRouter(prefix="/case-files", tags=["case-files"])


@router.post("", response_model=CaseFile, status_code=201)
def create_case_file(case_file: CaseFile | None = None) -> CaseFile:
    if case_file is None:
        case_file = CaseFile(session_id=str(uuid.uuid4()))
    elif not case_file.session_id:
        case_file.session_id = str(uuid.uuid4())
    return store_save(case_file)


@router.get("/{session_id}", response_model=CaseFile)
def get_case_file(session_id: str) -> CaseFile:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    return case_file


@router.put("/{session_id}", response_model=CaseFile)
def update_case_file(session_id: str, updates: dict) -> CaseFile:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    # model_copy(update=...) would set raw dict values without re-validating/
    # coercing them (e.g. a plain "Storage" string would never become the
    # OccupancyType enum member) - round-trip through model_validate instead
    # so every field goes through Pydantic's normal type coercion.
    merged = {**case_file.model_dump(), **updates}
    updated = CaseFile.model_validate(merged)
    updated.updated_at = datetime.now(timezone.utc)
    return store_save(updated)


@router.post("/{session_id}/classify", response_model=CaseFile)
def classify_case_file(session_id: str) -> CaseFile:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    case_file.classification_result = classify(case_file)
    case_file.conversation_stage = ConversationStage.CLASSIFIED
    case_file.updated_at = datetime.now(timezone.utc)
    return store_save(case_file)


@router.get("/{session_id}/report")
def get_report(session_id: str) -> dict:
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    return {"markdown": generate_report_markdown(case_file)}
