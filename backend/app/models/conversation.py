"""Conversation transcript data contract - Phase 2.

Until this existed, the chat transcript lived only in the frontend's React
state: switching away from the Overview page (or reopening a project from
Project History) lost every message, even though the structured facts the
conversation produced were safely persisted on the Case File. The Case File
is the source of truth for *what is known*; this is the record of *how it
was arrived at*.

Deliberately its own append-only table (see app/db/models.py's
ConversationMessageRecord), NOT a growing list inside the Case File's JSON
blob: a transcript grows unboundedly with every turn, and rewriting the
whole blob on each message - then shipping all of it on every Case File
response - gets quadratically worse as a project runs long. One row per
message, indexed by session_id and read back with a cursor, keeps an
append O(1) and lets a long conversation be paged instead of loaded whole.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class MessageKind(str, Enum):
    """How the frontend should render this message - mirrors the
    ConversationEntry union in frontend/src/pages/overview/conversation.ts.
    Stored rather than re-derived so a reloaded transcript renders exactly
    as it did live (a document result as its result card, a classification
    as its summary card), instead of collapsing to undifferentiated text.
    """

    TEXT = "text"
    DOCUMENT_RESULT = "document_result"
    CLASSIFICATION_RESULT = "classification_result"


class ConversationMessage(BaseModel):
    id: int
    session_id: str
    role: MessageRole
    kind: MessageKind = MessageKind.TEXT
    text: str = ""
    payload: Optional[dict] = Field(
        default=None,
        description=(
            "Structured data for a non-text kind: the IngestSummary for a "
            "document_result, the ClassificationResult for a "
            "classification_result. None for plain text messages."
        ),
    )
    created_at: datetime
