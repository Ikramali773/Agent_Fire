"""ORM model. One row per Case File, stored as a JSON blob keyed by
session_id - deliberately not a fully normalized relational schema.

Why: the Case File (backend/app/models/case_file.py) is a single Pydantic
aggregate with several nested structures (field_sources, classification_result,
source_documents) that all change together and are always read/written as a
whole - there's no query pattern yet that needs to filter on, say, "all case
files with height_m > 24" at the SQL level. Normalizing now would mean
hand-maintaining a second schema in lockstep with the Pydantic model for no
present benefit. The `created_at`/`updated_at` columns are pulled out
because those genuinely are useful to index/sort on independent of the blob.
Revisit if a real query need for individual fields shows up later.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CaseFileRecord(Base):
    __tablename__ = "case_files"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Phase 2 (accounts): pulled out alongside created_at/updated_at for the
    # same reason those are - genuinely useful to query/index on ("list my
    # case files") independent of the blob, even though it's also part of
    # CaseFile.owner_user_id inside `data`. Nullable: an anonymous (Phase 1
    # style) case file has no owner.
    owner_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class ConversationMessageRecord(Base):
    """One row per chat message - the one place in this schema that IS
    normalized rather than blob-stored, and for a specific reason (see
    app/models/conversation.py): a transcript is append-only and unbounded,
    so it must not live inside the Case File's JSON blob where every new
    message would rewrite (and re-ship) the whole history.

    The integer primary key is what gives a total ordering: two messages in
    the same turn (a user message and the agent's reply) can land in the
    same clock tick, so created_at alone is not a reliable sort key.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaseFileChangeRecord(Base):
    """One row per changed field - normalized for the same reason
    ConversationMessageRecord is (see app/models/change_log.py): a change
    log is append-only and unbounded, so it must not live inside the Case
    File's JSON blob where every edit would rewrite the whole history.

    The integer primary key gives a total ordering: one PUT can change
    several fields at once and they all land in the same clock tick, so
    created_at alone is not a reliable sort key.

    old_value/new_value are JSON columns rather than strings because a
    Case File field can be a scalar, a list (existing_fire_systems) or a
    list of objects (occupancy_breakdown, floor_wise_area) - stringifying
    them would make the log unable to show what actually changed.
    """

    __tablename__ = "case_file_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaseFileGrantRecord(Base):
    """Phase 3: one row per person a case file has been shared with.

    Its own table rather than a list on the Case File, for the same reason
    ownership is a column: "which case files can I see?" is a query, and
    answering it by scanning every row's JSON blob in Python does not
    survive a real number of projects.

    (session_id, granted_to_user_id) is unique - sharing with the same
    person twice is the same grant, not two.
    """

    __tablename__ = "case_file_grants"
    __table_args__ = (
        UniqueConstraint("session_id", "granted_to_user_id", name="uq_case_file_grant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    granted_to_user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    granted_to_email: Mapped[str] = mapped_column(String, nullable=False)
    granted_by_user_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaseFileReviewRecord(Base):
    """Phase 3: one row per review verdict - append-only, like the
    transcript and the change log.

    Never updated in place: a compliance sign-off's value is that the whole
    sequence is visible, including a case that was approved, reopened after
    a fact changed, and approved again. The CURRENT status is simply the
    latest row (see app/review_store.py::current_status).

    The integer primary key is the ordering, not created_at: two verdicts
    recorded in the same second must still have an unambiguous order.
    """

    __tablename__ = "case_file_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserRecord(Base):
    """Phase 2 (accounts). hashed_password never leaves app/auth/user_store.py -
    every API-facing model is app/models/user.py's User, which has no
    password field at all.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
