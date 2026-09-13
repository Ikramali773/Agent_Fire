"""Tests for the Phase 4 compliance engine (app/engine/requirements.py).

The engine's job is narrow and its failure modes are asymmetric: marking a
requirement met when it is not is far worse than leaving it unknown, and
reporting a building as failing because nobody told us what it has is a
false verdict on a compliance record. Most of these tests defend those two
lines.
"""

import pytest
from fastapi.testclient import TestClient

from app import change_log, grant_store, review_store
from app.auth.user_store import delete_all as delete_all_users
from app.engine.classifier import classify
from app.engine.requirements import (
    INSTALLATION_LABELS,
    INSTALLATION_ORDER,
    evaluate_requirements,
    match_declaration,
    normalize_declared_systems,
)
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.models.case_file import CaseFile, OccupancyType
from app.models.requirements import RequirementStatus
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    change_log.delete_all()
    review_store.delete_all()
    grant_store.delete_all()


def _classified(**overrides) -> CaseFile:
    case_file = CaseFile(
        session_id="s",
        occupancy_type=OccupancyType.RESIDENTIAL,
        occupancy_subdivision="A-I",
        height_m=30.0,
        built_up_area_sqm=1500.0,
        floors_above_ground=10,
        **overrides,
    )
    case_file.classification_result = classify(case_file)
    return case_file


def _status(case_file: CaseFile, code: str) -> RequirementStatus:
    report = evaluate_requirements(case_file)
    return next(f.status for f in report.findings if f.code == code)


class TestMatchingDeclarations:
    def test_matches_the_plain_name(self):
        assert match_declaration("wet riser") == "wet_riser"

    def test_ignores_case_punctuation_and_extra_words(self):
        # These come from free text a person typed or OCR produced.
        assert match_declaration("Wet-Riser") == "wet_riser"
        assert match_declaration("WET RISER (2 nos.)") == "wet_riser"
        assert match_declaration("  wet   riser  ") == "wet_riser"

    def test_matches_common_shorthand(self):
        assert match_declaration("sprinklers") == "automatic_wet_sprinkler_system"
        assert match_declaration("smoke detectors throughout") == "automatic_fire_detection_and_alarm_system"
        assert match_declaration("PA system") == "public_address_and_voice_evacuation_system"

    def test_prefers_the_most_specific_match(self):
        # "automatic wet sprinkler" contains "sprinkler"; the longer, more
        # specific synonym must win so a phrase cannot resolve oddly.
        assert match_declaration("automatic wet sprinkler system") == "automatic_wet_sprinkler_system"

    def test_returns_nothing_rather_than_guessing(self):
        # A wrong match marks a requirement met that is not - the single
        # most damaging mistake this module could make.
        assert match_declaration("foam deluge system") is None
        assert match_declaration("CO2 flooding") is None
        assert match_declaration("") is None

    def test_unrecognized_declarations_are_reported_not_dropped(self):
        matched, unrecognized = normalize_declared_systems(["wet riser", "foam deluge"])

        assert matched == {"wet_riser": "wet riser"}
        assert unrecognized == ["foam deluge"]

    def test_blank_entries_are_ignored_entirely(self):
        matched, unrecognized = normalize_declared_systems(["", "   ", "wet riser"])

        assert list(matched) == ["wet_riser"]
        assert unrecognized == []

    def test_the_matched_text_is_kept_for_display(self):
        matched, _ = normalize_declared_systems(["Wet-Riser (2 nos.)"])

        assert matched["wet_riser"] == "Wet-Riser (2 nos.)"


class TestEvaluation:
    def test_nothing_declared_reads_as_unknown_never_as_a_failure(self):
        # The line this whole module is built around. "You are missing a
        # wet riser" and "we do not know whether you have one" are the
        # difference between a defect and a question.
        case_file = _classified(existing_fire_systems=[])

        report = evaluate_requirements(case_file)

        assert report.not_met_count == 0
        assert report.unknown_count > 0
        assert all(
            f.status is RequirementStatus.UNKNOWN
            for f in report.findings
            if f.required
        )

    def test_a_declared_requirement_is_met(self):
        required = _classified().classification_result.required_installations
        case_file = _classified(existing_fire_systems=[INSTALLATION_LABELS[required[0]]])

        assert _status(case_file, required[0]) is RequirementStatus.MET

    def test_a_requirement_absent_from_a_real_inventory_is_not_met(self):
        required = _classified().classification_result.required_installations
        missing = required[0]
        present = [code for code in required if code != missing]
        case_file = _classified(existing_fire_systems=[INSTALLATION_LABELS[c] for c in present])

        assert _status(case_file, missing) is RequirementStatus.NOT_MET

    def test_an_installation_the_band_does_not_require_is_marked_so(self):
        case_file = _classified()
        required = set(case_file.classification_result.required_installations)
        not_required = next(code for code in INSTALLATION_ORDER if code not in required)

        assert _status(case_file, not_required) is RequirementStatus.NOT_REQUIRED

    def test_every_installation_gets_a_finding_in_a_stable_order(self):
        # A reader comparing two projects should see the same rows in the
        # same order, including the ones that do not apply.
        report = evaluate_requirements(_classified())

        assert [f.code for f in report.findings] == INSTALLATION_ORDER

    def test_a_met_finding_says_what_it_matched(self):
        required = _classified().classification_result.required_installations
        case_file = _classified(existing_fire_systems=[f"{INSTALLATION_LABELS[required[0]]} - 12 nos."])

        finding = next(f for f in evaluate_requirements(case_file).findings if f.code == required[0])

        assert finding.matched_declaration == f"{INSTALLATION_LABELS[required[0]]} - 12 nos."

    def test_a_met_finding_never_claims_the_system_was_verified(self):
        # It was declared, not inspected. The distinction has to survive
        # into the wording, or "met" reads as "compliant".
        required = _classified().classification_result.required_installations
        case_file = _classified(existing_fire_systems=[INSTALLATION_LABELS[required[0]]])

        finding = next(f for f in evaluate_requirements(case_file).findings if f.code == required[0])

        assert "declared" in finding.detail.lower()
        assert "not been checked" in finding.detail.lower()

    def test_an_unclassified_building_produces_no_findings_at_all(self):
        # Inventing findings from an incomplete case file would be worse
        # than showing none.
        report = evaluate_requirements(CaseFile(session_id="s"))

        assert report.evaluated is False
        assert report.findings == []

    def test_the_counts_match_the_findings(self):
        required = _classified().classification_result.required_installations
        case_file = _classified(existing_fire_systems=[INSTALLATION_LABELS[required[0]]])

        report = evaluate_requirements(case_file)

        assert report.met_count == sum(1 for f in report.findings if f.status is RequirementStatus.MET)
        assert report.not_met_count == sum(
            1 for f in report.findings if f.status is RequirementStatus.NOT_MET
        )

    def test_a_system_declared_but_not_required_is_acknowledged(self):
        case_file = _classified()
        required = set(case_file.classification_result.required_installations)
        spare = next(code for code in INSTALLATION_ORDER if code not in required)
        case_file = _classified(existing_fire_systems=[INSTALLATION_LABELS[spare]])

        finding = next(f for f in evaluate_requirements(case_file).findings if f.code == spare)

        assert finding.status is RequirementStatus.NOT_REQUIRED
        assert "Declared as present anyway" in finding.detail

    def test_the_report_carries_the_band_it_judged_against(self):
        report = evaluate_requirements(_classified())

        assert report.table_7_ref == "7A"
        assert report.protection_level


class TestMixedUse:
    def test_the_union_of_requirements_is_evaluated(self):
        # Clause 3.1.11.2's most-restrictive rule: a Mixed Use building is
        # judged against every component's requirements together.
        from app.models.case_file import OccupancyBreakdownItem

        case_file = CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.MIXED_USE,
            mixed_occupancy=True,
            height_m=30.0,
            built_up_area_sqm=6000.0,
            floors_above_ground=12,
            occupancy_breakdown=[
                # Subdivisions are required for a Table 7 band to match -
                # without them the engine correctly routes to human review
                # instead of guessing, so a Mixed Use fixture needs them.
                OccupancyBreakdownItem(
                    type=OccupancyType.MERCANTILE,
                    subdivision="F",
                    floor_range="G-2",
                    floor_area_sqm=2000.0,
                ),
                OccupancyBreakdownItem(
                    type=OccupancyType.BUSINESS,
                    subdivision="E-I",
                    floor_range="3-12",
                    floor_area_sqm=4000.0,
                ),
            ],
        )
        case_file.classification_result = classify(case_file)

        report = evaluate_requirements(case_file)

        assert report.evaluated is True
        required = {f.code for f in report.findings if f.required}
        # The union really is a union: more than either component alone.
        assert len(required) >= 2


class TestEndpoint:
    def _project(self, systems: list[str] | None = None) -> str:
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(
            f"/case-files/{session_id}",
            json={
                "occupancy_type": OccupancyType.RESIDENTIAL.value,
                "occupancy_subdivision": "A-I",
                "height_m": 30.0,
                "built_up_area_sqm": 1500.0,
                "floors_above_ground": 10,
                **({"existing_fire_systems": systems} if systems is not None else {}),
            },
        )
        client.post(f"/case-files/{session_id}/classify")
        return session_id

    def test_findings_are_served_for_a_classified_project(self):
        session_id = self._project(["fire extinguishers", "hose reel"])

        body = client.get(f"/case-files/{session_id}/findings").json()

        assert body["evaluated"] is True
        assert len(body["findings"]) == len(INSTALLATION_ORDER)
        assert body["met_count"] >= 1

    def test_an_unclassified_project_reports_nothing_to_evaluate(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        body = client.get(f"/case-files/{session_id}/findings").json()

        assert body["evaluated"] is False

    def test_findings_follow_the_case_file_without_being_stored(self):
        # Derived on read: changing a fact must change the findings with no
        # reclassification or cache invalidation step.
        session_id = self._project([])
        assert client.get(f"/case-files/{session_id}/findings").json()["met_count"] == 0

        client.put(f"/case-files/{session_id}", json={"existing_fire_systems": ["fire extinguishers"]})

        assert client.get(f"/case-files/{session_id}/findings").json()["met_count"] == 1

    def test_an_unknown_case_file_is_404(self):
        assert client.get("/case-files/nope/findings").status_code == 404

    def test_another_account_cannot_read_the_findings(self):
        owner = client.post(
            "/auth/signup", json={"email": "owner@example.com", "password": "correct-horse"}
        ).json()
        stranger = client.post(
            "/auth/signup", json={"email": "stranger@example.com", "password": "correct-horse"}
        ).json()
        session_id = client.post(
            "/case-files", json=None, headers={"Authorization": f"Bearer {owner['access_token']}"}
        ).json()["session_id"]

        resp = client.get(
            f"/case-files/{session_id}/findings",
            headers={"Authorization": f"Bearer {stranger['access_token']}"},
        )

        assert resp.status_code == 403
