"""Turns whatever text a pipeline tier produced (Tiers 1-3's OCR/text-layer
output, or Tier 4's vision-model transcription - fact extraction doesn't
care which tier it came from) into Case File field values.

Deliberately reuses LLMClient.extract_fields - the exact same structured-
extraction machinery the conversational Dialogue Manager uses on a chat
reply (app/dialogue/manager.py). A document is just another source of text
describing the building; the fact that it came from a file rather than a
typed message doesn't need its own extraction logic.
"""

from __future__ import annotations

from typing import Literal

from app.dialogue.nodes import OCCUPANCY_OPTIONS
from app.llm.client import LLMClient
from app.models.case_file import FloorAreaItem

DOCUMENT_FIELD_TYPES: dict[str, type] = {
    "project_name": str,
    "state": str,
    "city": str,
    "occupancy_type": Literal[tuple(OCCUPANCY_OPTIONS)],  # type: ignore[valid-type]
    "height_m": float,
    "floors_above_ground": int,
    "floors_below_ground": int,
    "built_up_area_sqm": float,
    "floor_wise_area": list[FloorAreaItem],
    "number_of_staircases": int,
    "number_of_exits": int,
    "existing_fire_systems": list[str],
}

_CONTEXT = (
    "This text was extracted from an uploaded document (an architectural "
    "plan title block, an existing NOC letter, or an architect's "
    "certificate) - not typed directly by the user. Only fill in a field "
    "if the document text actually states it. A drawing's 'area statement' "
    "or similar schedule (often marked '[Table(s) detected on this page]' "
    "in this text, with rows separated by ' | ') usually gives "
    "floor_wise_area - one entry per floor/level with its own area_sqm, "
    "distinct from built_up_area_sqm which is the whole building's total."
)


def extract_case_file_facts(text: str, llm: LLMClient) -> dict:
    if not text.strip():
        return {}
    return llm.extract_fields(text, DOCUMENT_FIELD_TYPES, context=_CONTEXT)
