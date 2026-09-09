"""Report Generator - product scope section B.9.

Templated + prose sections. No LLM call lives here: this module only ever
restates facts already present on the Case File / ClassificationResult. Where
the scope doc calls for "LLM prose" (e.g. turning a clause reference into a
plain-language explanation), that is a distinct, later integration point -
deliberately not required for the deterministic parts of the report to be
correct and shippable on their own.
"""

from __future__ import annotations

from datetime import date

from app.engine import state_checklists
from app.models.case_file import CaseFile, FieldSourceKind

_DISCLAIMER = (
    "This report is advisory only and does not constitute statutory approval. "
    "Final compliance determination rests with the appropriate licensed fire "
    "officer/architect/authority."
)

_FIELD_SOURCE_LABEL = {
    FieldSourceKind.USER: "confirmed by user",
    FieldSourceKind.DOCUMENT: "extracted from document",
    FieldSourceKind.INFERRED: "estimated",
    FieldSourceKind.UNKNOWN: "unknown",
}


def _fmt(value) -> str:
    if value is None:
        return "Not provided"
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _case_summary_lines(case_file: CaseFile) -> list[str]:
    lines = []
    plain_fields = [
        ("Project name", case_file.project_name),
        ("State", case_file.state),
        ("City", case_file.city),
        ("Occupancy", _fmt(case_file.occupancy_type)),
        ("Occupancy subdivision", _fmt(case_file.occupancy_subdivision)),
        ("Industrial hazard band", _fmt(case_file.industrial_hazard_band)),
        ("Height (m)", _fmt(case_file.height_m)),
        ("Floors above ground", _fmt(case_file.floors_above_ground)),
        ("Floors below ground", _fmt(case_file.floors_below_ground)),
        ("Built-up area (sqm)", _fmt(case_file.built_up_area_sqm)),
        ("Number of staircases", _fmt(case_file.number_of_staircases)),
        ("Number of exits", _fmt(case_file.number_of_exits)),
        (
            "Existing fire systems",
            ", ".join(case_file.existing_fire_systems) if case_file.existing_fire_systems else "None declared",
        ),
    ]
    for label, value in plain_fields:
        source = case_file.field_sources.get(label)
        source_tag = f" _({_FIELD_SOURCE_LABEL[source.source]})_" if source else ""
        lines.append(f"- **{label}:** {value}{source_tag}")
    return lines


def _state_checklist_lines(case_file: CaseFile) -> list[str]:
    if not case_file.state:
        return ["- State not specified yet - no checklist to show."]

    checklist = state_checklists.get_checklist_for_state(case_file.state)
    if checklist is None:
        return [
            f"- No NOC checklist is available yet for {case_file.state} - "
            "currently only Gujarat and Maharashtra have one wired up (and, "
            "as of this report, even those are placeholders - see below)."
        ]

    lines = [f"- Checklist ID: `{checklist['checklist_id']}`"]
    if checklist["status"] == "placeholder":
        lines.append(f"- ⚠ **PLACEHOLDER — NOT A REAL GOVERNMENT CHECKLIST.** {checklist['disclaimer']}")
    else:
        lines.append(f"- Source: {checklist.get('source') or 'Not recorded'}")
    for item in checklist["items"]:
        lines.append(f"  - {item}")
    return lines


def generate_report_markdown(case_file: CaseFile) -> str:
    result = case_file.classification_result
    today = date.today().isoformat()

    lines: list[str] = []
    lines.append(f"# Fire Safety & NOC Readiness Report — {case_file.project_name or 'Untitled Project'}")
    lines.append(
        f"Generated: {today} | Based on NBCS 2026 Part F (primary, edition {case_file.code_edition.value}) "
        f"| State: {case_file.state or 'Not specified'}"
    )
    lines.append("")

    lines.append("## 1. Case Summary")
    lines.extend(_case_summary_lines(case_file))
    lines.append("")

    lines.append("## 2. Classification")
    occ = _fmt(case_file.occupancy_type)
    if case_file.industrial_hazard_band:
        occ += f" [{case_file.industrial_hazard_band.value}]"
    high_rise = "Yes" if result.is_high_rise else ("No" if result.is_high_rise is False else "Unknown")
    lines.append(
        f"Occupancy: {occ}  |  Applies to NBCS Part F mandatory scope: {_fmt(result.applies)}  |  "
        f"High Rise: {high_rise} (height_m >= 24)  |  Table 7 Reference: {result.table_7_ref or 'N/A'}"
        + ("  |  ⚠ HUMAN REVIEW REQUIRED" if result.require_human_review_flag else "")
    )
    lines.append("")

    lines.append("## 3. Applicable NBCS Part F Requirements")
    if result.applicable_clauses:
        for clause in result.applicable_clauses:
            lines.append(f"- {clause}")
    else:
        lines.append("- No applicable clauses determined yet.")
    lines.append("")

    lines.append("## 4. State NOC Checklist")
    lines.extend(_state_checklist_lines(case_file))
    lines.append("")

    lines.append("## 5. Gaps Identified / Notes")
    if result.notes:
        for note in result.notes:
            lines.append(f"- {note}")
    else:
        lines.append("- None identified.")
    lines.append("")

    lines.append("## 6. Disclaimer")
    lines.append(_DISCLAIMER)

    return "\n".join(lines)
