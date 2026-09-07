"""Deterministic classification engine - NBCS 2026 Part F.

Implements the logic described in the product scope document, section B.6.3.
This is plain code, not an LLM call: every branch here must be traceable back
to a specific clause in the digitized rule data (data/rules/nbcs_2026_partf/).

Guardrail (Part G, Principle 1): the LLM layer may explain these results in
prose, but it must never be allowed to invent or override them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine import rules_loader
from app.models.case_file import (
    CaseFile,
    ClassificationResult,
    IndustrialHazardBand,
    OccupancyType,
)

# Occupancies that carry a mandatory human/expert review flag regardless of
# how confident the deterministic lookup is (product scope B.6.3 / B.12).
_MANDATORY_REVIEW_OCCUPANCIES = {OccupancyType.INSTITUTIONAL, OccupancyType.HAZARDOUS}

_COMPARATOR_SUFFIXES = ("_gte", "_gt", "_lte", "_lt")


@dataclass
class BandMatch:
    subdivision: str
    band_id: str
    condition_text: str
    confidence: str  # "explicit" | "interpreted"
    installations: Optional[dict]
    note: Optional[str] = None


@dataclass
class Table7LookupResult:
    table_ref: str  # e.g. "7A"
    self_certification_applies: bool
    matched_bands: list[BandMatch] = field(default_factory=list)
    ambiguous: bool = False


class ClassificationError(ValueError):
    """Raised when the case file is missing a fact required to classify."""


def _split_comparator_key(key: str) -> tuple[str, str] | None:
    for suffix in _COMPARATOR_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)], suffix[1:]
    return None


def _clause_matches(clause: dict, facts: dict) -> bool:
    """A clause (dict of criteria) matches if every key in it holds against
    facts. An empty clause ({}) always matches - used for unconditional bands.
    A criterion referencing a fact the case file doesn't have (None) fails to
    match, rather than being silently skipped - we never guess a fact.
    """
    for key, expected in clause.items():
        split = _split_comparator_key(key)
        if split is None:
            # Plain equality criterion, e.g. "has_rack_storage": true
            actual = facts.get(key)
            if actual != expected:
                return False
            continue
        field_name, op = split
        actual = facts.get(field_name)
        if actual is None:
            return False
        if op == "gte" and not (actual >= expected):
            return False
        if op == "gt" and not (actual > expected):
            return False
        if op == "lte" and not (actual <= expected):
            return False
        if op == "lt" and not (actual < expected):
            return False
    return True


def _band_matches(structured_criteria: dict, facts: dict) -> bool:
    return any(
        _clause_matches(clause, facts) for clause in structured_criteria.get("match_any", [])
    )


def check_applicability(
    occupancy_key: str,
    hazard_band: Optional[IndustrialHazardBand],
    height_m: Optional[float],
    area_sqm: Optional[float],
) -> tuple[bool, str]:
    """Clause 1.2 applicability gate: height OR area, whichever is exceeded
    first (area-only for Industrial G-1/G-2). Returns (applies, note).
    """
    thresholds = rules_loader.get_applicability_thresholds()["thresholds"]

    lookup_key = occupancy_key
    if occupancy_key == "Industrial":
        if hazard_band is None:
            raise ClassificationError(
                "industrial_hazard_band is required to check applicability for Industrial occupancy"
            )
        band_label = {
            IndustrialHazardBand.G1_LOW: "Industrial - Low hazard",
            IndustrialHazardBand.G2_MODERATE: "Industrial - Moderate hazard",
            IndustrialHazardBand.G3_HIGH: "Industrial - High hazard",
        }[hazard_band]
        lookup_key = band_label

    row = next((r for r in thresholds if r["occupancy"] == lookup_key), None)
    if row is None:
        raise ClassificationError(f"No applicability threshold row found for '{lookup_key}'")

    if height_m is None or area_sqm is None:
        raise ClassificationError(
            "height_m and built_up_area_sqm are both required to check applicability"
        )

    if row["logic"] == "area_only":
        applies = area_sqm > row["floor_area_sqm"]
    else:
        height_exceeds = row["height_m"] is not None and height_m > row["height_m"]
        area_exceeds = row["floor_area_sqm"] is not None and area_sqm > row["floor_area_sqm"]
        applies = height_exceeds or area_exceeds

    if applies:
        return True, ""

    note = (
        "Below NBCS 2026 Part F's mandatory scope for this occupancy "
        "(clause 1.2). State/local bye-laws may still apply, and note that "
        "state/local authorities may modify these thresholds for local fire "
        "vulnerability/preparedness (clause 1.2, Note 1)."
    )
    return False, note


SINGLE_STAIRCASE_SURVIVOR_NOTE = (
    "Clause 1.2, Note 2: even though this building falls below the "
    "mandatory-scope threshold, a single-staircase building must still "
    "provide a firefighting-shaft-type staircase on the external periphery, "
    "with both lobby and stairwell ventilated (minimum 1.6 sqm opening "
    "through fixed louvres kept permanently open), a 2 h fire door for the "
    "lobby, and a 1 h fire door for the stairwell."
)


def compute_is_high_rise(height_m: Optional[float]) -> Optional[bool]:
    """Clause 2.39: occupancy-independent, height_m >= 24."""
    if height_m is None:
        return None
    return height_m >= 24


def _facts_from_case_file(case_file: CaseFile) -> dict:
    return {
        "height_m": case_file.height_m,
        "area_sqm": case_file.built_up_area_sqm,
        "floors_above_ground": case_file.floors_above_ground,
        # Not yet part of the Case File schema (B.4) - included so a band
        # that references them fails safe (no fact -> clause doesn't match)
        # rather than raising, until these fields are added.
        "ridge_height_m": None,
        "has_rack_storage": None,
    }


def lookup_table7(
    occupancy_key: str,
    hazard_band: Optional[IndustrialHazardBand],
    case_file: CaseFile,
) -> Table7LookupResult:
    group_letter = rules_loader.group_letter_for_occupancy(occupancy_key)
    if group_letter == "K":
        raise ClassificationError(
            "Mixed Use has no dedicated Table 7 - use lookup_mixed_use() instead"
        )

    table = rules_loader.get_table7(group_letter)
    table_ref = f"7{group_letter}"

    self_cert = table.get("self_certification_threshold")
    self_cert_applies = False
    if self_cert and case_file.height_m is not None and case_file.built_up_area_sqm is not None:
        self_cert_applies = (
            case_file.built_up_area_sqm <= self_cert["area_sqm_max"]
            and case_file.height_m <= self_cert["height_m_max"]
        )

    facts = _facts_from_case_file(case_file)

    rows = table["rows"]
    if group_letter == "G":
        subdivision_key = {
            IndustrialHazardBand.G1_LOW: "G-1",
            IndustrialHazardBand.G2_MODERATE: "G-2",
            IndustrialHazardBand.G3_HIGH: "G-3",
        }.get(hazard_band)
        if subdivision_key is None:
            raise ClassificationError("industrial_hazard_band is required to look up Table 7G")
        rows = [r for r in rows if r["subdivision"] == subdivision_key]
    elif len({r["subdivision"] for r in rows}) > 1:
        # Table has multiple genuinely different subdivisions (e.g. 7A's A-I
        # lodging house vs A-V starred hotel) - never match across all of
        # them silently, that would blend unrelated R/NR grids together.
        if case_file.occupancy_subdivision is None:
            raise ClassificationError(
                f"Table {table_ref} has multiple subdivisions "
                f"({sorted({r['subdivision'] for r in rows})}) - "
                "case_file.occupancy_subdivision must be set to disambiguate "
                "before a band can be matched."
            )
        rows = [r for r in rows if r["subdivision"] == case_file.occupancy_subdivision]
        if not rows:
            raise ClassificationError(
                f"occupancy_subdivision '{case_file.occupancy_subdivision}' does not "
                f"match any subdivision in Table {table_ref}"
            )

    matched: list[BandMatch] = []
    for row in rows:
        for band in row["bands"]:
            criteria = band.get("structured_criteria")
            if criteria and _band_matches(criteria, facts):
                matched.append(
                    BandMatch(
                        subdivision=row.get("subdivision_name", row.get("subdivision", "")),
                        band_id=band["band_id"],
                        condition_text=band["condition"],
                        confidence=criteria.get("confidence", "unknown"),
                        installations=band.get("installations"),
                        note=band.get("note"),
                    )
                )

    return Table7LookupResult(
        table_ref=table_ref,
        self_certification_applies=self_cert_applies,
        matched_bands=matched,
        ambiguous=len(matched) > 1,
    )


def classify(case_file: CaseFile) -> ClassificationResult:
    result = ClassificationResult()

    if case_file.occupancy_type is None:
        result.notes.append("occupancy_type is required before classification can run.")
        return result

    occupancy_key = case_file.occupancy_type.value

    if occupancy_key == "Mixed Use":
        result.notes.append(
            "Mixed Use classification requires per-component occupancy breakdown "
            "(case_file.occupancy_breakdown) - union-of-clauses logic is not yet "
            "implemented in this engine; route to human review."
        )
        result.require_human_review_flag = True
        return result

    try:
        applies, note = check_applicability(
            occupancy_key,
            case_file.industrial_hazard_band,
            case_file.height_m,
            case_file.built_up_area_sqm,
        )
    except ClassificationError as exc:
        result.notes.append(str(exc))
        return result

    result.applies = applies

    if case_file.number_of_staircases == 1:
        result.notes.append(SINGLE_STAIRCASE_SURVIVOR_NOTE)

    if not applies:
        result.notes.append(note)
        return result

    result.is_high_rise = compute_is_high_rise(case_file.height_m)

    try:
        lookup = lookup_table7(occupancy_key, case_file.industrial_hazard_band, case_file)
    except ClassificationError as exc:
        result.notes.append(str(exc))
        result.require_human_review_flag = True
        return result
    result.table_7_ref = lookup.table_ref

    if lookup.self_certification_applies:
        result.notes.append(
            f"Within Table {lookup.table_ref}'s self-certification threshold: "
            "self-certification by a certified and State-approved building "
            "professional is treated as acceptable in place of the full "
            "installation requirements below."
        )

    if not lookup.matched_bands:
        result.notes.append(
            f"No Table {lookup.table_ref} band matched this building's height/area "
            "- likely means the source table only gives a hydraulic-calculation "
            "note for this range (see the table's 'SEE_NOTE' bands) or the case "
            "needs additional facts. Route to human review."
        )
        result.require_human_review_flag = True
    else:
        band = lookup.matched_bands[0]
        result.protection_level = band.band_id
        result.applicable_clauses.append(
            f"Table {lookup.table_ref} band {band.band_id} ({band.subdivision}): {band.condition_text}"
        )
        if band.installations:
            required = [k for k, v in band.installations.items() if v == "R"]
            result.applicable_clauses.append(
                f"Required installations: {', '.join(required)}"
            )
        if band.confidence == "interpreted":
            result.notes.append(
                f"Table {lookup.table_ref} band {band.band_id} was matched using an "
                "INTERPRETED reading of a compound height/area condition in the "
                "source table (see the rule data file's band_matching_convention "
                "note). Verify against the source document before treating this "
                "as final."
            )
        if lookup.ambiguous:
            result.notes.append(
                f"More than one Table {lookup.table_ref} band matched this "
                "building's height/area - the most specific/first match was used. "
                "Review the other candidate bands before finalizing."
            )
            result.require_human_review_flag = True

    if result.is_high_rise:
        annex_d = rules_loader.get_annex_d_high_rise()
        result.applicable_clauses.append(
            f"High Rise (height >= 24 m, clause 2.39): {annex_d['title']} (Annex D) "
            "applies in addition to the Table 7 requirements above."
        )

    if case_file.occupancy_type in _MANDATORY_REVIEW_OCCUPANCIES:
        result.require_human_review_flag = True
        result.notes.append(
            f"{case_file.occupancy_type.value} occupancy carries a mandatory "
            "human/expert review flag - never present this classification as "
            "fully automated or final without specialist consultation."
        )

    return result
