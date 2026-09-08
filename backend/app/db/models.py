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

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CaseFileRecord(Base):
    __tablename__ = "case_files"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
