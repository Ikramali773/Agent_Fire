"""Question-tree node definitions - product scope section B.5.

Each node fills one or more Case File fields. "Skip anything already known"
(B.5's design principle) is implemented by checking `field_sources` - a field
counts as filled the moment it has a source entry, regardless of value, so a
node is never re-asked once answered (including "none" / empty-list answers).

Deliberately deferred for this pass (see backend/README.md): the Node 0
document-upload branch offering itself proactively inside the guided flow
(the upload endpoint and widget exist, but the dialogue manager doesn't yet
suggest it as a step for every goal, only renewal - see Node 2a in
manager.py). The linear spine (location -> goal -> occupancy ->
[occupancy_breakdown for Mixed Use] -> [hazard band] -> [subdivision] ->
height -> area -> [egress -> existing systems, skipped by Node 3a] -> confirm
-> classify) is what's implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from app.engine import rules_loader
from app.models.case_file import CaseFile, OccupancyBreakdownItem, OccupancyType

# Occupancies where Table 7's bands genuinely differ by subdivision (see
# backend/app/models/case_file.py's occupancy_subdivision docstring) - only
# these get the extra subdivision question.
SUBDIVISION_OPTIONS: dict[str, dict[str, str]] = {
    "Residential": {
        "A-I": "Lodging or rooming house",
        "A-II": "Dormitory / hostel",
        "A-III": "Apartment house",
        "A-IV": "Hotel (up to 4-star)",
        "A-V": "Starred hotel (5-star and above)",
    },
    "Institutional": {
        "C_NURSING": "Nursing home / sanatorium",
        "C-I": "Hospital",
        "C-II_C-III": "Custodial, penal, or mental institution",
    },
    "Business": {
        "E-I": "Business (human occupied)",
        "E-II": "Data centre",
    },
    "Mercantile": {
        "F": "Mercantile (general shops/stores)",
        "F-II": "Underground shopping complex",
    },
}

OCCUPANCY_OPTIONS = [
    "Residential",
    "Educational",
    "Institutional",
    "Assembly",
    "Business",
    "Mercantile",
    "Industrial",
    "Storage",
    "Hazardous",
    "Mixed Use",
]

GOAL_OPTIONS = {
    "understand_requirements": "Understand requirements for a new design",
    "prep_noc": "Prep for a NOC filing",
    "renew_noc": "Renew an existing NOC",
    "general_qa": "Just have general questions as I go",
}


@dataclass
class Node:
    id: str
    field_types: dict[str, type]
    prompt: Callable[[CaseFile], str]
    context: str = ""
    applicable: Callable[[CaseFile], bool] = lambda case_file: True

    def is_filled(self, case_file: CaseFile) -> bool:
        if not self.field_types:
            return False  # a zero-field node (e.g. confirm) is never "pre-filled"
        return all(name in case_file.field_sources for name in self.field_types)


def _occupancy_literal() -> type:
    return Literal[tuple(OCCUPANCY_OPTIONS)]  # type: ignore[valid-type]


def _goal_literal() -> type:
    return Literal[tuple(GOAL_OPTIONS.keys())]  # type: ignore[valid-type]


def _subdivision_literal(case_file: CaseFile) -> type:
    options = SUBDIVISION_OPTIONS.get(
        case_file.occupancy_type.value if case_file.occupancy_type else "", {}
    )
    return Literal[tuple(options.keys())]  # type: ignore[valid-type]


def residential_self_cert_eligible(case_file: CaseFile) -> bool:
    """Node 3a: the residential early-exit shortcut. True once a Residential
    building's height and area are both known and fall within Table 7A's own
    self-certification threshold (read from the digitized rule data, not a
    hardcoded copy of it - see data/rules/nbcs_2026_partf/table7/
    table7a_residential.json's self_certification_threshold) - at that point
    classify() will report self-certification as sufficient regardless of
    egress/existing-systems detail, so asking those questions first only
    delays a result the engine already knows.
    """
    if case_file.occupancy_type != OccupancyType.RESIDENTIAL:
        return False
    if case_file.height_m is None or case_file.built_up_area_sqm is None:
        return False
    threshold = rules_loader.get_table7("A").get("self_certification_threshold")
    if not threshold:
        return False
    return (
        case_file.built_up_area_sqm <= threshold["area_sqm_max"]
        and case_file.height_m <= threshold["height_m_max"]
    )


NODES: list[Node] = [
    Node(
        id="location",
        field_types={"state": str, "city": str},
        prompt=lambda cf: "Which state and city is the project in?",
    ),
    Node(
        id="goal",
        field_types={"goal": _goal_literal()},
        prompt=lambda cf: (
            "What are you trying to do — understand requirements for a new "
            "design, prep for a NOC filing, renew an existing NOC, or just "
            "have general questions as you go?"
        ),
        context=f"Valid goal values: {list(GOAL_OPTIONS.keys())} (map the user's phrasing to one of these).",
    ),
    Node(
        id="occupancy",
        field_types={"occupancy_type": _occupancy_literal()},
        prompt=lambda cf: (
            "What's the primary use of the building? Residential / "
            "Educational / Institutional (e.g. hospital) / Assembly (e.g. "
            "hall, theatre, mall) / Business (offices) / Mercantile (shops) "
            "/ Industrial / Storage / Hazardous / Mixed Use"
        ),
        context=f"Valid occupancy_type values: {OCCUPANCY_OPTIONS}.",
    ),
    Node(
        id="occupancy_breakdown",
        field_types={"occupancy_breakdown": list[OccupancyBreakdownItem]},
        prompt=lambda cf: (
            "Since this is a Mixed Use building, list each occupancy present "
            "and its approximate floor area — e.g. 'ground floor retail "
            "(Mercantile), 800 sqm; floors 1–5 residential apartments, 4500 "
            "sqm total'."
        ),
        context=(
            "Extract each occupancy component as an item with: type (one of "
            f"{[o for o in OCCUPANCY_OPTIONS if o != 'Mixed Use']} — never "
            "'Mixed Use' itself for a component), floor_range (free text like "
            "'G' or '1-5'), floor_area_sqm (that component's OWN approximate "
            "floor area, not the whole building's), and subdivision only if "
            "clearly implied (e.g. a starred/5-star hotel component -> "
            "'A-V'; an underground shopping complex component -> 'F-II')."
        ),
        applicable=lambda cf: cf.occupancy_type is not None and cf.occupancy_type.value == "Mixed Use",
    ),
    Node(
        id="hazard_band",
        field_types={"industrial_hazard_band": Literal["G-1", "G-2", "G-3"]},
        prompt=lambda cf: (
            "What's the hazard classification of the industrial processes "
            "involved — low hazard (G-1), moderate hazard (G-2), or high "
            "hazard (G-3)?"
        ),
        context="Map the user's description to G-1 (low), G-2 (moderate), or G-3 (high).",
        applicable=lambda cf: (
            (cf.occupancy_type is not None and cf.occupancy_type.value == "Industrial")
            or any(item.type == OccupancyType.INDUSTRIAL for item in cf.occupancy_breakdown)
        ),
    ),
    Node(
        id="subdivision",
        field_types={"occupancy_subdivision": str},  # Literal computed dynamically below
        prompt=lambda cf: (
            "Which of these best describes it?\n"
            + "\n".join(
                f"- {code}: {label}"
                for code, label in SUBDIVISION_OPTIONS.get(cf.occupancy_type.value, {}).items()
            )
        ),
        context="",  # filled dynamically per-call in manager.py
        applicable=lambda cf: cf.occupancy_type is not None
        and cf.occupancy_type.value in SUBDIVISION_OPTIONS,
    ),
    Node(
        id="height",
        field_types={"height_m": float, "floors_above_ground": int, "floors_below_ground": int},
        prompt=lambda cf: (
            "What's the building height (in meters), and how many floors "
            "above and below ground?"
        ),
    ),
    Node(
        id="area",
        field_types={"built_up_area_sqm": float},
        prompt=lambda cf: (
            "What's the approximate built-up area in square meters (per "
            "floor or total — whatever you have)?"
        ),
    ),
    Node(
        id="egress",
        field_types={"number_of_staircases": int, "number_of_exits": int},
        prompt=lambda cf: "How many staircases and exits does the building currently have (or are planned)?",
        applicable=lambda cf: not residential_self_cert_eligible(cf),
    ),
    Node(
        id="existing_systems",
        field_types={"existing_fire_systems": list[str]},
        prompt=lambda cf: (
            "Do you already have any fire-safety systems in place — "
            "extinguishers, fire alarm, sprinklers, hydrants, wet/dry riser? "
            "List whatever applies, or say 'none yet.'"
        ),
        applicable=lambda cf: not residential_self_cert_eligible(cf),
    ),
]
"""Data-collecting nodes only (Node 1-7 of B.5). The confirmation step
(Node 8) and classification (Node 9) are driven by CaseFile.conversation_stage
in dialogue/manager.py instead of being a Node here, since "has the user
confirmed" isn't a Case File field to fill - see manager.py for why."""


def next_node(case_file: CaseFile) -> Node | None:
    for node in NODES:
        if not node.applicable(case_file):
            continue
        if not node.is_filled(case_file):
            return node
    return None
