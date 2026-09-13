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

from app.models.case_file import CaseFile
from app.models.requirements import RequirementFinding, RequirementReport, RequirementStatus

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


def _normalize(text: str) -> str:
    """Lowercased, punctuation flattened to single spaces - so "Wet-Riser",
    "wet riser" and "WET RISER (2 nos.)" all compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def match_declaration(declaration: str) -> str | None:
    """The installation code a declared system refers to, or None.

    Longest synonym first, so "automatic wet sprinkler" is not claimed by
    the shorter "sprinkler" entry of the same installation, and so a
    phrasing that contains another installation's name as a substring
    resolves to the more specific one.
    """
    normalized = _normalize(declaration)
    if not normalized:
        return None
    candidates = [
        (len(_normalize(synonym)), code)
        for code, synonyms in _SYNONYMS.items()
        for synonym in synonyms
        if _normalize(synonym) in normalized
    ]
    if not candidates:
        return None
    return max(candidates)[1]


def normalize_declared_systems(declarations: list[str]) -> tuple[dict[str, str], list[str]]:
    """Splits free-text declarations into {code: the text it matched} and
    the ones nothing recognised."""
    matched: dict[str, str] = {}
    unrecognized: list[str] = []
    for declaration in declarations:
        if not declaration or not declaration.strip():
            continue
        code = match_declaration(declaration)
        if code is None:
            unrecognized.append(declaration.strip())
        else:
            matched.setdefault(code, declaration.strip())
    return matched, unrecognized


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
        )

    declared, unrecognized = normalize_declared_systems(case_file.existing_fire_systems)
    nothing_declared = not case_file.existing_fire_systems

    findings: list[RequirementFinding] = []
    for code in INSTALLATION_ORDER:
        label = INSTALLATION_LABELS[code]
        if code not in required:
            # Worth saying when a building has something it does not need:
            # the reader would otherwise wonder whether their declaration
            # was understood at all.
            extra = (
                " Declared as present anyway."
                if code in declared
                else ""
            )
            findings.append(
                RequirementFinding(
                    code=code,
                    label=label,
                    status=RequirementStatus.NOT_REQUIRED,
                    required=False,
                    detail=f"Table {result.table_7_ref} does not require this for this building.{extra}",
                    matched_declaration=declared.get(code),
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
        met_count=sum(1 for f in findings if f.status is RequirementStatus.MET),
        not_met_count=sum(1 for f in findings if f.status is RequirementStatus.NOT_MET),
        unknown_count=sum(1 for f in findings if f.status is RequirementStatus.UNKNOWN),
    )
