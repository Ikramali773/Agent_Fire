"""Compliance engine - per-requirement evaluation, Phase 4.

Plain code, like app/engine/classifier.py, and held to the same rule: every
verdict here must be traceable to the digitized rule data plus a fact the
Case File actually records. Nothing is inferred, and no requirement exists
here that Table 7 does not state.

The comparison is deliberately narrow. A requirement is "met" when the
building has DECLARED the installation - not when the installation has been
verified to exist, to cover the right areas, or to be correctly designed.
That is a different and much harder question (it needs the plans, which is
the rest of Phase 4), and every surface that renders these findings says so
rather than letting "met" read as "compliant".
"""

from __future__ import annotations

import re

from app.engine import occupant_load
from app.models.case_file import CaseFile
from app.models.requirements import (
    OccupantLoadEstimate,
    RequirementFinding,
    RequirementReport,
    RequirementStatus,
)

# The eight installations Table 7 scores every band against, in the order a
# report reads best: detection first, then the manual/first-response kit,
# then the water-based systems, then evacuation.
INSTALLATION_ORDER = [
    "automatic_fire_detection_and_alarm_system",
    "fire_extinguisher",
    "first_aid_hose_reel",
    "down_comer",
    "wet_riser",
    "yard_hydrant",
    "automatic_wet_sprinkler_system",
    "public_address_and_voice_evacuation_system",
]

INSTALLATION_LABELS = {
    "automatic_fire_detection_and_alarm_system": "Automatic fire detection and alarm system",
    "fire_extinguisher": "Fire extinguishers",
    "first_aid_hose_reel": "First-aid hose reel",
    "down_comer": "Down-comer",
    "wet_riser": "Wet riser",
    "yard_hydrant": "Yard hydrant",
    "automatic_wet_sprinkler_system": "Automatic wet sprinkler system",
    "public_address_and_voice_evacuation_system": "Public address and voice evacuation system",
}

# How a person writes each installation, versus the rule data's key.
# `existing_fire_systems` is free text the user typed or a document
# yielded, so it has to be matched rather than compared.
#
# Deliberately conservative: these are phrasings that can only mean the one
# installation. Anything not matched here is reported as unrecognized, never
# guessed at - a wrong match would mark a requirement met that is not, which
# is the single most damaging mistake this module could make.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "automatic_fire_detection_and_alarm_system": (
        "automatic fire detection and alarm",
        "fire detection and alarm",
        "fire alarm",
        "detection and alarm",
        "smoke detector",
        "smoke detection",
        "heat detector",
        "fire detection",
        "alarm system",
    ),
    "fire_extinguisher": ("fire extinguisher", "extinguisher", "portable extinguisher"),
    "first_aid_hose_reel": ("first aid hose reel", "hose reel", "first-aid hose"),
    "down_comer": ("down comer", "downcomer", "down-comer"),
    "wet_riser": ("wet riser", "wet-riser", "rising main"),
    "yard_hydrant": ("yard hydrant", "external hydrant", "hydrant"),
    "automatic_wet_sprinkler_system": (
        "automatic wet sprinkler",
        "wet sprinkler",
        "sprinkler system",
        "sprinklers",
        "sprinkler",
    ),
    "public_address_and_voice_evacuation_system": (
        "public address and voice evacuation",
        "voice evacuation",
        "public address",
        "pa system",
        "voice alarm",
    ),
}


# Words that turn a mention of an installation into a statement that it is
# NOT there. Without these, "no sprinklers" reads as a declared sprinkler
# system and marks the requirement met - crediting a building for the exact
# thing its owner just said it lacks, which is the worst mistake this
# module can make. "to be provided" and friends are the same case: a system
# that is planned is not a system that exists.
_ABSENCE_MARKERS = (
    "no ",
    "not ",
    "non ",
    "nil",
    "none",
    "absent",
    "without",
    "n a",
    "missing",
    "lacking",
    "to be provided",
    "to be installed",
    "proposed",
    "planned",
    "future",
    "tbd",
    "pending",
    "under installation",
    "out of order",
    "defunct",
    "non functional",
    "not working",
)

# One entry often names several systems ("fire extinguishers, hose reel and
# wet riser"), so an entry is split before matching - otherwise only one is
# credited and the rest read as missing, which is a false failure on a
# compliance record. Splitting also scopes negation, so "wet riser
# installed, no sprinklers" says one of each.
_SEGMENT_SEPARATORS = re.compile(r"[,;/\n]")
# Splitting on " and " is conditional (see _clauses): two of the eight
# installations have "and" in their own names - "automatic fire detection
# AND alarm system", "public address AND voice evacuation system" - so
# splitting unconditionally would cut a single system in half and quote
# back half its name as the evidence.
_CONJUNCTIONS = re.compile(r" and | & | plus | but | with ", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Lowercased, punctuation flattened to single spaces - so "Wet-Riser",
    "wet riser" and "WET RISER (2 nos.)" all compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _stem(text: str) -> str:
    """Normalized, with a trailing plural "s" dropped from each word.

    People write "fire extinguishers" and the rule data says
    "fire_extinguisher". Matching is word-bounded (so a synonym cannot be
    found inside an unrelated word), which means the plural has to be
    handled rather than relying on a bare substring test. Crude, but both
    sides go through it and it only ever compares against a fixed
    eight-installation vocabulary.

    Applied to MATCHING only, never to the absence check: "(2 nos.)" would
    stem to "no" and read as a negation.
    """
    return " ".join(
        word[:-1] if len(word) > 3 and word.endswith("s") else word
        for word in _normalize(text).split()
    )


# Precomputed once: normalizing every synonym on every declaration was
# pointless work, and doing it here keeps the matcher's cost proportional
# to what the user actually typed.
_NORMALIZED_SYNONYMS: list[tuple[int, str, str]] = sorted(
    (
        (len(_stem(synonym)), _stem(synonym), code)
        for code, synonyms in _SYNONYMS.items()
        for synonym in synonyms
    ),
    reverse=True,
)


def asserts_absence(declaration: str) -> bool:
    """Whether this text says the system is NOT there (or not there yet)."""
    padded = f" {_normalize(declaration)} "
    return any(f" {marker.strip()} " in padded or padded.startswith(f" {marker.strip()} ") for marker in _ABSENCE_MARKERS)


def match_declaration(declaration: str) -> str | None:
    """The installation code a declared system refers to, or None.

    Longest synonym first, so "automatic wet sprinkler" is not claimed by
    the shorter "sprinkler" entry of the same installation, and so a
    phrasing that contains another installation's name as a substring
    resolves to the more specific one.
    """
    codes = match_all_declarations(declaration)
    return codes[0] if codes else None


def match_all_declarations(declaration: str) -> list[str]:
    """Every installation named in one piece of text, most specific first.

    Deduplicated by code, so "automatic wet sprinkler system" (which
    contains the shorter "sprinkler" synonym of the same installation)
    counts once.
    """
    stemmed = _stem(declaration)
    if not stemmed:
        return []
    found: list[str] = []
    for _length, synonym, code in _NORMALIZED_SYNONYMS:
        if code in found:
            continue
        if f" {synonym} " in f" {stemmed} ":
            found.append(code)
    return found


def _clauses(segment: str) -> list[str]:
    """One segment, split on conjunctions only where that actually helps.

    Splitting is worth doing when it finds MORE systems than the whole
    segment does, or when the halves disagree about absence ("wet riser
    installed but no sprinklers"). Otherwise the segment is left alone, so
    an installation whose own name contains "and" survives intact and its
    full text is what gets quoted back as evidence.
    """
    parts = [part for part in _CONJUNCTIONS.split(segment) if part.strip()]
    if len(parts) < 2:
        return [segment]

    whole_codes = match_all_declarations(segment)
    part_codes = {code for part in parts for code in match_all_declarations(part)}
    absence_differs = len({asserts_absence(part) for part in parts}) > 1

    if len(part_codes) > len(whole_codes) or absence_differs:
        return parts
    return [segment]


def normalize_declared_systems(
    declarations: list[str],
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Splits free-text declarations into what is present, what is stated to
    be absent, and what nothing recognised - each as {code: the text}.

    A clause claiming absence is NOT simply dropped: "no wet riser" is more
    information than silence, and reporting it as "not recorded" would lose
    the user's own statement.
    """
    present: dict[str, str] = {}
    absent: dict[str, str] = {}
    unrecognized: list[str] = []
    for declaration in declarations:
        if not declaration or not declaration.strip():
            continue
        matched_anything = False
        for segment in _SEGMENT_SEPARATORS.split(declaration):
            for clause in _clauses(segment):
                codes = match_all_declarations(clause)
                if not codes:
                    continue
                matched_anything = True
                target = absent if asserts_absence(clause) else present
                for code in codes:
                    target.setdefault(code, clause.strip())
        if not matched_anything:
            unrecognized.append(declaration.strip())
    # A system named in one clause as present and another as absent is a
    # contradiction in the user's own input; absence wins, because crediting
    # it would be the dangerous reading.
    for code in list(present):
        if code in absent:
            del present[code]
    return present, absent, unrecognized


def _occupant_load(case_file: CaseFile, result) -> OccupantLoadEstimate | None:
    """Table 2's occupant load, alongside the findings but never one of them.

    Deliberately NOT a RequirementFinding: a finding carries a status, and
    an occupant load has none - it is a head count, not a verdict. Turning
    it into one needs the stair and exit widths in Table 3, which this
    Case File does not hold, and listing it among verdicts would invite it
    being read as one.
    """
    band = case_file.industrial_hazard_band
    estimate = occupant_load.compute(
        case_file.occupancy_type.value if case_file.occupancy_type else None,
        case_file.built_up_area_sqm,
        band.value if band else None,
    )
    if estimate is None:
        return None
    return OccupantLoadEstimate(
        resolved=estimate.resolved,
        people=estimate.people,
        low=estimate.low,
        high=estimate.high,
        explanation=estimate.explanation,
        caveats=estimate.caveats,
    )


def evaluate_requirements(case_file: CaseFile) -> RequirementReport:
    """Compares every Table 7 installation against what the building has
    declared.

    Returns an un-evaluated report when the building has not been
    classified: there is no matched band, so no requirement applies yet,
    and inventing findings from an incomplete case file would be worse than
    showing none.
    """
    result = case_file.classification_result
    required = set(result.required_installations)

    if not result.table_7_ref or not required:
        return RequirementReport(
            session_id=case_file.session_id,
            evaluated=False,
            table_7_ref=result.table_7_ref,
            protection_level=result.protection_level,
            # Reported even here: an occupant load needs only an occupancy
            # and an area, not a Table 7 band, so "how many people" is
            # answerable before the building has been classified. Withholding
            # it until then would hide a figure that is already known.
            occupant_load=_occupant_load(case_file, result),
        )

    declared, declared_absent, unrecognized = normalize_declared_systems(
        case_file.existing_fire_systems
    )
    nothing_declared = not case_file.existing_fire_systems

    findings: list[RequirementFinding] = []
    for code in INSTALLATION_ORDER:
        label = INSTALLATION_LABELS[code]
        if code not in required:
            # Worth saying when a building has something it does not need:
            # the reader would otherwise wonder whether their declaration
            # was understood at all.
            if code in declared:
                extra = " Declared as present anyway."
            elif code in declared_absent:
                extra = " Recorded as not present, which is fine - it is not required."
            else:
                extra = ""
            findings.append(
                RequirementFinding(
                    code=code,
                    label=label,
                    status=RequirementStatus.NOT_REQUIRED,
                    required=False,
                    detail=f"Table {result.table_7_ref} does not require this for this building.{extra}",
                    matched_declaration=declared.get(code) or declared_absent.get(code),
                )
            )
            continue

        if code in declared:
            findings.append(
                RequirementFinding(
                    code=code,
                    label=label,
                    status=RequirementStatus.MET,
                    required=True,
                    detail=(
                        f"Required by Table {result.table_7_ref}"
                        f"{f' band {result.protection_level}' if result.protection_level else ''}, "
                        "and declared as present. Declared only - this system's coverage, "
                        "specification and installation have not been checked."
                    ),
                    matched_declaration=declared[code],
                )
            )
        elif code in declared_absent:
            findings.append(
                RequirementFinding(
                    code=code,
                    label=label,
                    status=RequirementStatus.NOT_MET,
                    required=True,
                    detail=(
                        f"Required by Table {result.table_7_ref}"
                        f"{f' band {result.protection_level}' if result.protection_level else ''}, "
                        "and explicitly recorded as not present."
                    ),
                    matched_declaration=declared_absent[code],
                )
            )
        elif nothing_declared:
            findings.append(
                RequirementFinding(
                    code=code,
                    label=label,
                    status=RequirementStatus.UNKNOWN,
                    required=True,
                    detail=(
                        f"Required by Table {result.table_7_ref}, but no existing fire systems "
                        "have been recorded for this building, so whether it is present is "
                        "not known."
                    ),
                )
            )
        else:
            findings.append(
                RequirementFinding(
                    code=code,
                    label=label,
                    status=RequirementStatus.NOT_MET,
                    required=True,
                    detail=(
                        f"Required by Table {result.table_7_ref}"
                        f"{f' band {result.protection_level}' if result.protection_level else ''}, "
                        f"and not among the {len(case_file.existing_fire_systems)} system(s) "
                        "recorded for this building."
                    ),
                )
            )

    return RequirementReport(
        session_id=case_file.session_id,
        evaluated=True,
        table_7_ref=result.table_7_ref,
        protection_level=result.protection_level,
        findings=findings,
        unrecognized_declarations=unrecognized,
        occupant_load=_occupant_load(case_file, result),
        met_count=sum(1 for f in findings if f.status is RequirementStatus.MET),
        not_met_count=sum(1 for f in findings if f.status is RequirementStatus.NOT_MET),
        unknown_count=sum(1 for f in findings if f.status is RequirementStatus.UNKNOWN),
    )
