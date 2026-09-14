"""Occupant load (Table 2).

The one compliance number derivable from what a Case File already holds -
an area and an occupancy over the table's square-metres-per-person factor.

Most of these tests are about what it refuses to say. Table 2 gives several
factors for most occupancies, and picking one to produce a confident number
would be inventing the answer; some rows are not numbers at all.
"""

from __future__ import annotations

from app.engine.occupant_load import compute
from app.engine.requirements import evaluate_requirements as build_report
from app.models.case_file import CaseFile, IndustrialHazardBand, OccupancyType


class TestWhenItResolves:
    def test_a_single_factor_occupancy_gives_one_number(self):
        load = compute("Storage", 3000)

        assert load.resolved is True
        assert load.people == 100  # 3000 / 30

    def test_the_count_is_rounded_up(self):
        # A fraction of a person still needs somewhere to go.
        load = compute("Storage", 3001)

        assert load.people == 101

    def test_a_general_row_wins_over_its_subdivisions(self):
        # Plain Business has its own factor (7.1). Without this rule the
        # datacentre sub-rows (E-II, 10 and 20 gross) dragged an ordinary
        # office into a 50-141 range when the table answers it exactly.
        load = compute("Business", 1000)

        assert load.resolved is True
        assert load.people == 141

    def test_industrial_resolves_once_the_hazard_band_is_known(self):
        # The one multi-row group that resolves automatically, because the
        # classifier already determines the band.
        assert compute("Industrial", 2000).resolved is False
        assert compute("Industrial", 2000, "G-3").people == 200  # 2000 / 10

    def test_the_explanation_shows_the_arithmetic(self):
        # So a reader can check it rather than trust it.
        explanation = compute("Storage", 3000).explanation

        assert "3,000" in explanation and "30.0" in explanation and "100 people" in explanation


class TestWhenItRefusesToGuess:
    def test_several_possible_factors_give_a_range_not_a_number(self):
        # Institutional has four rows - nursing home, daycare clinic,
        # inpatient, outpatient - and which applies depends on the actual
        # sub-use, which the Case File does not record in those terms.
        load = compute("Institutional", 1000)

        assert load.resolved is False
        assert load.people is None
        assert (load.low, load.high) == (84, 143)

    def test_the_range_says_why_it_could_not_be_narrowed(self):
        explanation = compute("Institutional", 1000).explanation

        assert "depends on what the space is actually used for" in explanation

    def test_a_fixed_seating_factor_is_not_computed_from_area(self):
        # Those rows carry "see_note_fixed_seating" - counted by seats, not
        # by area. Computing with that string would be nonsense.
        load = compute("Assembly", 500)

        assert load.resolved is False
        assert "fixed seats" in load.explanation

    def test_no_occupancy_means_no_answer_at_all(self):
        # None, not zero: "we do not know" and "nobody is in this
        # building" are different answers.
        assert compute(None, 1000) is None

    def test_no_area_means_no_answer_at_all(self):
        assert compute("Storage", None) is None
        assert compute("Storage", 0) is None


class TestItIsNeverAVerdict:
    def test_every_result_says_it_is_not_a_pass_or_a_fail(self):
        # An occupant load on its own says nothing about compliance -
        # turning it into a required exit width needs Table 3's stair and
        # exit measurements, which the Case File does not hold.
        for load in (compute("Storage", 3000), compute("Institutional", 1000)):
            assert any("not a pass or a fail" in caveat for caveat in load.caveats)
            assert any("Table 3" in caveat for caveat in load.caveats)

    def test_every_result_admits_which_area_it_used(self):
        # Table 2 distinguishes net from gross floor area; the Case File
        # holds one built-up figure.
        assert any("net floor area from gross" in c for c in compute("Storage", 3000).caveats)

    def test_it_is_not_one_of_the_findings(self):
        # A finding carries a status. An occupant load has none, and
        # listing it among verdicts would invite it being read as one.
        case_file = CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.STORAGE,
            built_up_area_sqm=3000.0,
            height_m=12.0,
        )

        report = build_report(case_file)

        assert report.occupant_load is not None
        assert report.occupant_load.people == 100
        assert all("occupant" not in finding.installation.lower() for finding in report.findings)

    def test_a_case_file_with_no_area_reports_no_occupant_load(self):
        case_file = CaseFile(
            session_id="s", occupancy_type=OccupancyType.STORAGE, height_m=12.0
        )

        assert build_report(case_file).occupant_load is None

    def test_an_industrial_case_file_uses_its_recorded_band(self):
        case_file = CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.INDUSTRIAL,
            industrial_hazard_band=IndustrialHazardBand.G3_HIGH,
            built_up_area_sqm=2000.0,
            height_m=12.0,
        )

        report = build_report(case_file)

        assert report.occupant_load.resolved is True
        assert report.occupant_load.people == 200
