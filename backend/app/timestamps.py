"""Reattaching UTC to timestamps that lost their timezone.

SQLite has no timezone-aware type: a `DateTime(timezone=True)` column
happily stores what `datetime.now(timezone.utc)` wrote, then hands it back
with `tzinfo` set to None. Serialized, that becomes "2026-09-13T07:13:16"
with no offset - and a browser parsing an ISO string with no offset treats
it as LOCAL time, so a change made seconds ago reads as hours ago for every
user outside UTC.

The same applies to a Case File row written before this was fixed, whose
JSON blob holds a naive `created_at`/`updated_at` from the old
`datetime.utcnow()` default.

Every one of these values was written as UTC, so labelling a naive one as
UTC on the way out is a correction, not a guess.
"""

from __future__ import annotations

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Labels a naive timestamp as UTC; leaves an aware one alone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
