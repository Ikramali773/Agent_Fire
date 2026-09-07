"""Loads the digitized NBCS 2026 Part F rule data (data/rules/nbcs_2026_partf/)
into memory, cached for process lifetime.

Per product-scope Part G, Principle 1 ("LLM reasons and explains; deterministic
engines decide"), this module and classifier.py are the ONLY things allowed to
produce a classification result - never an LLM free-generation.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# backend/app/engine/rules_loader.py -> repo_root/data/rules/nbcs_2026_partf
_REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_DIR = _REPO_ROOT / "data" / "rules" / "nbcs_2026_partf"

_TABLE7_FILES = {
    "A": "table7a_residential.json",
    "B": "table7b_educational.json",
    "C": "table7c_institutional.json",
    "D": "table7d_assembly.json",
    "E": "table7e_business.json",
    "F": "table7f_mercantile.json",
    "G": "table7g_industrial.json",
    "H": "table7h_storage.json",
    "J": "table7j_hazardous.json",
}

# Maps the Case File's human-readable OccupancyType values to the NBCS group
# letter used throughout the rule data.
OCCUPANCY_TO_GROUP_LETTER = {
    "Residential": "A",
    "Educational": "B",
    "Institutional": "C",
    "Assembly": "D",
    "Business": "E",
    "Mercantile": "F",
    "Industrial": "G",
    "Storage": "H",
    "Hazardous": "J",
    "Mixed Use": "K",
}


def _load_json(filename: str) -> dict:
    path = RULES_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_meta() -> dict:
    return _load_json("meta.json")


@lru_cache(maxsize=1)
def get_applicability_thresholds() -> dict:
    return _load_json("applicability_thresholds.json")


@lru_cache(maxsize=1)
def get_group_k_separation_matrix() -> dict:
    return _load_json("group_k_mixed_occupancy_separation.json")


@lru_cache(maxsize=1)
def get_annex_d_high_rise() -> dict:
    return _load_json("annex_d_high_rise_summary.json")


@lru_cache(maxsize=None)
def get_table7(group_letter: str) -> dict:
    """Table 7A-7J for a given occupancy group letter (A, B, C, ... J).

    Raises KeyError for Group K (Mixed Use), which has no dedicated Table 7 -
    callers must instead union the component occupancies' tables per clause
    3.1.11.2.
    """
    filename = _TABLE7_FILES[group_letter]
    return _load_json(f"table7/{filename}")


def group_letter_for_occupancy(occupancy_type: str) -> str:
    return OCCUPANCY_TO_GROUP_LETTER[occupancy_type]
