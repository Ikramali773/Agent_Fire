"""Case File change log data contract - the "what changed, and when".

The Case File records *what is known* and the conversation transcript
(app/models/conversation.py) records *how it was said*; neither answers the
question a reviewer actually asks about a compliance case - "this building
was 24 m yesterday and 68 m today; who changed it, and off the back of
what?". Project History was a project *list* for exactly this reason: it
showed each case file's current state with no per-field timeline behind it.

Scope, deliberately: this logs Case File FACTS. The classification outcome
is not duplicated here - every classification is already stored in the
transcript as a structured `classification_result` message with its full
payload, and a second copy would be one more thing to keep in step. The
`conversation_stage` transition to "classified" IS logged, so the timeline
still shows when it happened and lines up with that message.

`field_sources` is likewise excluded: it changes alongside nearly every
field, so logging it would double the length of the timeline to say what
each entry's own `source` already says.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChangeSource(str, Enum):
    """Where a change came from. Mirrors the provenance vocabulary the Case
    File already uses for `field_sources`, plus the two ways a value can be
    set without a person typing it.
    """

    USER = "user"
    """Edited directly - the Case File page's click-to-edit, via PUT."""

    DIALOGUE = "dialogue"
    """Extracted from something the user said in the conversation."""

    DOCUMENT = "document"
    """Extracted from an uploaded drawing or letter by the ingest pipeline."""

    SYSTEM = "system"
    """Set by the app itself, e.g. a conversation-stage transition."""


class FieldChange(BaseModel):
    id: int
    session_id: str
    field: str
    old_value: Optional[Any] = Field(
        default=None,
        description="The JSON value before the change. None for a field that had no value.",
    )
    new_value: Optional[Any] = Field(
        default=None,
        description="The JSON value after the change. None if the field was cleared.",
    )
    source: ChangeSource
    actor_user_id: Optional[str] = Field(
        default=None,
        description="The account that caused the change, when there was one. None for an anonymous session.",
    )
    created_at: datetime
