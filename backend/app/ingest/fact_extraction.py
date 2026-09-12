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

from app.dialogue.nodes import OCCUPANCY_OPTIONS, SUBDIVISION_OPTIONS
from app.llm.client import LLMClient
from app.models.case_file import FloorAreaItem

# Flattened across every occupancy's subdivision codes (see
# dialogue/nodes.py's SUBDIVISION_OPTIONS) rather than a per-occupancy
# Literal, since a document's occupancy_type and occupancy_subdivision are
# extracted in the same call - which subset would even apply isn't known
# ahead of time the way it is for the chat intake's dedicated subdivision
# node. An invalid/mismatched code is still safe: the classifier's Table 7
# lookup only accepts a subdivision that actually exists in that occupancy's
# table (see app/engine/classifier.py), routing to human review otherwise
# rather than silently misclassifying.
_ALL_SUBDIVISION_CODES = tuple(
    code for options in SUBDIVISION_OPTIONS.values() for code in options
)

DOCUMENT_FIELD_TYPES: dict[str, type] = {
    "project_name": str,
    "state": str,
    "city": str,
    "occupancy_type": Literal[tuple(OCCUPANCY_OPTIONS)],  # type: ignore[valid-type]
    "occupancy_subdivision": Literal[_ALL_SUBDIVISION_CODES],  # type: ignore[valid-type]
    "height_m": float,
    "floors_above_ground": int,
    "floors_below_ground": int,
    "built_up_area_sqm": float,
    "floor_wise_area": list[FloorAreaItem],
    "number_of_staircases": int,
    "number_of_exits": int,
    "existing_fire_systems": list[str],
    "kitchen_count": int,
    "door_count": int,
}

_SUBDIVISION_GLOSSARY = "; ".join(
    f"{occupancy}: " + ", ".join(f"{code} ({label})" for code, label in options.items())
    for occupancy, options in SUBDIVISION_OPTIONS.items()
)

_CONTEXT = (
    "This text was extracted from an uploaded document (an architectural "
    "plan title block, an existing NOC letter, or an architect's "
    "certificate) - not typed directly by the user. Only fill in a field "
    "if the document text actually states it. A drawing's 'area statement' "
    "or similar schedule (often marked '[Table(s) detected on this page]' "
    "in this text, with rows separated by ' | ') usually gives "
    "floor_wise_area - one entry per floor/level with its own area_sqm, "
    "distinct from built_up_area_sqm which is the whole building's total. "
    "Only fill occupancy_subdivision if occupancy_type is one of these and "
    f"the document clearly implies which: {_SUBDIVISION_GLOSSARY}. "
    "kitchen_count and door_count are simple counts (how many kitchens, how "
    "many doors total) if the document states or a door/room schedule "
    "table implies them - not a full schedule with sizes or fire ratings."
)


def extract_case_file_facts(text: str, llm: LLMClient) -> dict:
    if not text.strip():
        return {}
    return llm.extract_fields(text, DOCUMENT_FIELD_TYPES, context=_CONTEXT)
