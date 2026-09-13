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

from app.engine import rules_loader, state_checklists
from app.models.case_file import (
    CaseFile,
    ClassificationResult,
    IndustrialHazardBand,
    OccupancyType,
)
from app.models.review import ReviewReason, ReviewReasonCode

# Occupancies that carry a mandatory human/expert review flag regardless of
# how confident the deterministic lookup is (product scope B.6.3 / B.12).
_MANDATORY_REVIEW_OCCUPANCIES = {OccupancyType.INSTITUTIONAL, OccupancyType.HAZARDOUS}

_COMPARATOR_SUFFIXES = ("_gte", "_gt", "_lte", "_lt")


def _flag_review(result: ClassificationResult, code: ReviewReasonCode, detail: str) -> None:
    """The ONE way this engine says "a person has to look at this".

    Sets the flag, records the typed reason and appends the same prose to
    `notes` together, so the three can never drift apart. Before Phase 3
    each of the call sites below set the flag and appended a note by hand -
    exactly the shape of code where one branch eventually flags without
    explaining, or explains without flagging.
    """
    result.require_human_review_flag = True
    result.review_reasons.append(ReviewReason(code=code, detail=detail))
    result.notes.append(detail)


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


def _build_facts(
    height_m: Optional[float],
    area_sqm: Optional[float],
    floors_above_ground: Optional[int],
) -> dict:
    return {
        "height_m": height_m,
        "area_sqm": area_sqm,
        "floors_above_ground": floors_above_ground,
        # Not yet part of the Case File schema (B.4) - included so a band
        # that references them fails safe (no fact -> clause doesn't match)
        # rather than raising, until these fields are added.
        "ridge_height_m": None,
        "has_rack_storage": None,
    }


def lookup_table7(
    occupancy_key: str,
    hazard_band: Optional[IndustrialHazardBand],
    height_m: Optional[float],
    area_sqm: Optional[float],
    floors_above_ground: Optional[int] = None,
    occupancy_subdivision: Optional[str] = None,
) -> Table7LookupResult:
    """Looks up a single occupancy's Table 7 band from explicit facts rather
    than a CaseFile, so the same lookup can serve both a single-occupancy
    building (classify(), passing the whole building's own facts) and one
    component of a Mixed Use building (classify_mixed_use(), passing that
    component's own floor_area_sqm/subdivision against the shared building
    height_m) without duplicating this logic.
    """
    group_letter = rules_loader.group_letter_for_occupancy(occupancy_key)
    if group_letter == "K":
        raise ClassificationError(
            "Mixed Use has no dedicated Table 7 - use classify_mixed_use() instead"
        )

    table = rules_loader.get_table7(group_letter)
    table_ref = f"7{group_letter}"

    self_cert = table.get("self_certification_threshold")
    self_cert_applies = False
    if self_cert and height_m is not None and area_sqm is not None:
        self_cert_applies = (
            area_sqm <= self_cert["area_sqm_max"] and height_m <= self_cert["height_m_max"]
        )

    facts = _build_facts(height_m, area_sqm, floors_above_ground)

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
        if occupancy_subdivision is None:
            raise ClassificationError(
                f"Table {table_ref} has multiple subdivisions "
                f"({sorted({r['subdivision'] for r in rows})}) - "
                "occupancy_subdivision must be set to disambiguate before a "
                "band can be matched."
            )
        rows = [r for r in rows if r["subdivision"] == occupancy_subdivision]
        if not rows:
            raise ClassificationError(
                f"occupancy_subdivision '{occupancy_subdivision}' does not "
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
    """Entry point used by dialogue/manager.py. Dispatches to the single-
    occupancy path or classify_mixed_use(), then attaches the state NOC
    checklist ID (§B.10) either way - state and occupancy are independent
    axes, so this must not live inside either classification path itself.
    """
    if case_file.occupancy_type is None:
        result = ClassificationResult()
        result.notes.append("occupancy_type is required before classification can run.")
        result.applicable_state_checklist_id = state_checklists.checklist_id_for_state(
            case_file.state
        )
        return result

    occupancy_key = case_file.occupancy_type.value

    if occupancy_key == "Mixed Use":
        result = classify_mixed_use(case_file)
    else:
        result = _classify_single_occupancy(case_file, occupancy_key)

    result.applicable_state_checklist_id = state_checklists.checklist_id_for_state(case_file.state)
    return result


def _classify_single_occupancy(case_file: CaseFile, occupancy_key: str) -> ClassificationResult:
    result = ClassificationResult()

    # FIRST, before anything that can return early. This flag is "regardless
    # of how confident the deterministic lookup is" (B.6.3/B.12), and that
    # includes the case where Part F turns out not to apply at all: an
    # Institutional or Hazardous building below the applicability threshold
    # is exactly the kind of call nobody should be taking from an automated
    # answer. It previously sat after the "does not apply" early return, so
    # those cases came back unflagged.
    if case_file.occupancy_type in _MANDATORY_REVIEW_OCCUPANCIES:
        _flag_review(
            result,
            ReviewReasonCode.MANDATORY_OCCUPANCY,
            f"{case_file.occupancy_type.value} occupancy carries a mandatory "
            "human/expert review flag - never present this classification as "
            "fully automated or final without specialist consultation.",
        )

    try:
        applies, note = check_applicability(
            occupancy_key,
            case_file.industrial_hazard_band,
            case_file.height_m,
            case_file.built_up_area_sqm,
        )
    except ClassificationError as exc:
        # Being unable to decide applicability IS the definition of needing
        # a person. This used to append the note and return unflagged,
        # while the identical failure one step later (the Table 7 lookup)
        # did flag - the same blocker reaching the user two different ways
        # depending on which line it happened on.
        _flag_review(result, ReviewReasonCode.CLASSIFICATION_ERROR, str(exc))
        return result

    result.applies = applies

    if case_file.number_of_staircases == 1:
        result.notes.append(SINGLE_STAIRCASE_SURVIVOR_NOTE)

    if not applies:
        result.notes.append(note)
        return result

    result.is_high_rise = compute_is_high_rise(case_file.height_m)

    try:
        lookup = lookup_table7(
            occupancy_key,
            case_file.industrial_hazard_band,
            case_file.height_m,
            case_file.built_up_area_sqm,
            case_file.floors_above_ground,
            case_file.occupancy_subdivision,
        )
    except ClassificationError as exc:
        _flag_review(result, ReviewReasonCode.CLASSIFICATION_ERROR, str(exc))
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
        _flag_review(
            result,
            ReviewReasonCode.NO_BAND_MATCHED,
            f"No Table {lookup.table_ref} band matched this building's height/area "
            "- likely means the source table only gives a hydraulic-calculation "
            "note for this range (see the table's 'SEE_NOTE' bands) or the case "
            "needs additional facts. Route to human review.",
        )
    else:
        band = lookup.matched_bands[0]
        result.protection_level = band.band_id
        result.applicable_clauses.append(
            f"Table {lookup.table_ref} band {band.band_id} ({band.subdivision}): {band.condition_text}"
        )
        if band.installations:
            required = [k for k, v in band.installations.items() if v == "R"]
            # Kept structured as well as narrated: the sentence below is for
            # a reader, the list is what the compliance engine evaluates.
            result.required_installations = sorted(required)
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
            _flag_review(
                result,
                ReviewReasonCode.AMBIGUOUS_BAND,
                f"More than one Table {lookup.table_ref} band matched this "
                "building's height/area - the most specific/first match was used. "
                "Review the other candidate bands before finalizing.",
            )

    if result.is_high_rise:
        annex_d = rules_loader.get_annex_d_high_rise()
        result.applicable_clauses.append(
            f"High Rise (height >= 24 m, clause 2.39): {annex_d['title']} (Annex D) "
            "applies in addition to the Table 7 requirements above."
        )

    return result


def _separation_matrix_key(
    occupancy_key: str, hazard_band: Optional[IndustrialHazardBand]
) -> str:
    """Maps a component's occupancy (+ hazard band, for Industrial) to the
    key used in the Group K separation matrix's rows/columns - the matrix
    splits Industrial into three keys (Industrial-Low/Moderate/High) rather
    than one, unlike everywhere else in this engine.
    """
    if occupancy_key != "Industrial":
        return occupancy_key
    if hazard_band is None:
        raise ClassificationError(
            "industrial_hazard_band is required for an Industrial component of a "
            "Mixed Use building"
        )
    return {
        IndustrialHazardBand.G1_LOW: "Industrial-Low(G-1)",
        IndustrialHazardBand.G2_MODERATE: "Industrial-Moderate(G-2)",
        IndustrialHazardBand.G3_HIGH: "Industrial-High(G-3)",
    }[hazard_band]


def classify_mixed_use(case_file: CaseFile) -> ClassificationResult:
    """Clause 3.1.11 (Group K / Mixed Occupancy), product scope §B.6.3.

    Per data/rules/nbcs_2026_partf/group_k_mixed_occupancy_separation.json's
    own "application_rule": a mixed-use building's fire protection is
    governed by the MOST RESTRICTIVE provisions among the individual
    occupancies present (a union of each component's own Table 7 band, not
    an average or a single blended lookup), plus a pairwise fire-separation
    rating between every two occupancies actually present - and some pairs
    are flatly "NP" (not permitted), which this treats as a hard human-review
    trigger rather than something to silently paper over.

    Each component is classified against the *whole building's* height_m
    (one physical building has one height) but its *own* floor_area_sqm
    (Table 7 bands are height/area-driven, and a component's footprint is
    what actually determines its band) - see OccupancyBreakdownItem's
    docstring for why floor_area_sqm exists beyond the original B.4 schema.
    """
    result = ClassificationResult()
    result.table_7_ref = "K (union of component Table 7 bands + separation matrix, clause 3.1.11)"

    breakdown = case_file.occupancy_breakdown
    if len(breakdown) < 2:
        _flag_review(
            result,
            ReviewReasonCode.INCOMPLETE_MIXED_BREAKDOWN,
            "Mixed Use classification needs at least two occupancy_breakdown "
            f"components (case_file.occupancy_breakdown) - only {len(breakdown)} given.",
        )
        return result

    component_keys: list[str] = []
    any_applies = False
    all_matched_bands: list[BandMatch] = []
    mandatory_review_component = False

    for item in breakdown:
        occupancy_key = item.type.value

        if occupancy_key == "Mixed Use":
            _flag_review(
                result,
                ReviewReasonCode.INVALID_MIXED_COMPONENT,
                "A Mixed Use component cannot itself be 'Mixed Use' - skipped; "
                "list its actual occupancies instead.",
            )
            continue

        if item.type in _MANDATORY_REVIEW_OCCUPANCIES:
            mandatory_review_component = True

        hazard_band = case_file.industrial_hazard_band if occupancy_key == "Industrial" else None

        try:
            component_keys.append(_separation_matrix_key(occupancy_key, hazard_band))
        except ClassificationError as exc:
            _flag_review(result, ReviewReasonCode.CLASSIFICATION_ERROR, str(exc))
            continue

        if item.floor_area_sqm is None:
            _flag_review(
                result,
                ReviewReasonCode.MISSING_COMPONENT_AREA,
                f"{occupancy_key} component ({item.floor_range}) has no floor_area_sqm - "
                "cannot classify this component; route to human review.",
            )
            continue

        try:
            applies, _note = check_applicability(
                occupancy_key, hazard_band, case_file.height_m, item.floor_area_sqm
            )
        except ClassificationError as exc:
            _flag_review(
                result,
                ReviewReasonCode.CLASSIFICATION_ERROR,
                f"{occupancy_key} component ({item.floor_range}): {exc}",
            )
            continue
        if applies:
            any_applies = True

        try:
            lookup = lookup_table7(
                occupancy_key,
                hazard_band,
                case_file.height_m,
                item.floor_area_sqm,
                case_file.floors_above_ground,
                item.subdivision,
            )
        except ClassificationError as exc:
            _flag_review(
                result,
                ReviewReasonCode.CLASSIFICATION_ERROR,
                f"{occupancy_key} component ({item.floor_range}): {exc}",
            )
            continue

        if not lookup.matched_bands:
            _flag_review(
                result,
                ReviewReasonCode.NO_BAND_MATCHED,
                f"No Table {lookup.table_ref} band matched the {occupancy_key} component "
                f"({item.floor_range}) - route to human review.",
            )
            continue

        band = lookup.matched_bands[0]
        all_matched_bands.append(band)
        result.applicable_clauses.append(
            f"[{occupancy_key}, {item.floor_range}] Table {lookup.table_ref} band "
            f"{band.band_id} ({band.subdivision}): {band.condition_text}"
        )
        if band.confidence == "interpreted":
            result.notes.append(
                f"{occupancy_key} component band {band.band_id} was matched using an "
                "INTERPRETED reading of a compound height/area condition - verify "
                "against the source document before treating this as final."
            )
        if lookup.ambiguous:
            _flag_review(
                result,
                ReviewReasonCode.AMBIGUOUS_BAND,
                f"More than one Table {lookup.table_ref} band matched the "
                f"{occupancy_key} component ({item.floor_range}) - the most specific/"
                "first match was used. Review the other candidate bands.",
            )

    result.applies = any_applies if component_keys else None

    if all_matched_bands:
        # A single cross-occupancy protection_level isn't meaningful (a
        # Business "HL-2" and a Storage "CL-4" aren't on the same scale), so
        # rather than invent a ranking, expose the union of every matched
        # band's required installations - this IS the "most restrictive
        # provisions" rule from clause 3.1.11.2, just computed field-by-field
        # instead of picking one band to represent the whole building.
        union_required: set[str] = set()
        for band in all_matched_bands:
            if band.installations:
                union_required.update(k for k, v in band.installations.items() if v == "R")
        if union_required:
            result.required_installations = sorted(union_required)
            result.applicable_clauses.append(
                "Union of installations required across all occupancies present "
                f"('most restrictive provisions', clause 3.1.11.2): {', '.join(sorted(union_required))}"
            )

    separation_matrix = rules_loader.get_group_k_separation_matrix()["matrix"]
    seen_pairs: set[frozenset[str]] = set()
    not_permitted_pairs: list[tuple[str, str]] = []
    for i, key_a in enumerate(component_keys):
        for key_b in component_keys[i + 1 :]:
            pair = frozenset((key_a, key_b))
            if key_a == key_b or pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            rating = separation_matrix.get(key_a, {}).get(key_b)
            if rating is None:
                rating = separation_matrix.get(key_b, {}).get(key_a)
            if rating is None:
                _flag_review(
                    result,
                    ReviewReasonCode.MISSING_SEPARATION_RATING,
                    f"No separation rating found between {key_a} and {key_b} in the "
                    "Group K separation matrix - route to human review.",
                )
            elif rating == "NP":
                not_permitted_pairs.append((key_a, key_b))
            else:
                result.applicable_clauses.append(
                    f"Separation required between {key_a} and {key_b}: {rating} minutes "
                    "fire resistance rating (clause 3.1.11.1)."
                )

    for key_a, key_b in not_permitted_pairs:
        _flag_review(
            result,
            ReviewReasonCode.NOT_PERMITTED_COMBINATION,
            f"⚠ {key_a} and {key_b} is a NOT PERMITTED occupancy combination "
            "per the Group K separation table (clause 3.1.11) - this combination "
            "requires either a design change or specialist/authority approval.",
        )

    if case_file.number_of_staircases == 1:
        result.notes.append(SINGLE_STAIRCASE_SURVIVOR_NOTE)

    result.is_high_rise = compute_is_high_rise(case_file.height_m)
    if result.is_high_rise:
        annex_d = rules_loader.get_annex_d_high_rise()
        result.applicable_clauses.append(
            f"High Rise (height >= 24 m, clause 2.39): {annex_d['title']} (Annex D) "
            "applies in addition to the requirements above."
        )

    if mandatory_review_component:
        _flag_review(
            result,
            ReviewReasonCode.MANDATORY_OCCUPANCY,
            "This Mixed Use building includes an Institutional and/or Hazardous "
            "component, which carries a mandatory human/expert review flag - never "
            "present this classification as fully automated or final without "
            "specialist consultation.",
        )

    return result
