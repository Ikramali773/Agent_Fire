"""Occupant load (NBCS 2026 Part F, Table 2).

The one compliance number this product can actually derive from what a
Case File already holds: a floor area and an occupancy divided by the
table's square-metres-per-person factor.

It is deliberately **informational, never a verdict**. Occupant load on its
own says nothing about whether a building complies - that needs exit and
staircase widths (Table 3) to turn a head count into a required capacity,
and those are not Case File fields. Presenting this as a pass or a fail
would be inventing a conclusion out of half the inputs, which is exactly
what the rest of this engine refuses to do.

Two things the table makes harder than it looks, and which this module
refuses to paper over:

  * **Several groups have more than one row.** Institutional alone has
    four (nursing home, daycare clinic, inpatient, outpatient) with factors
    from 7 to 12 m2/person. Which applies depends on the actual sub-use,
    which the Case File does not record in those terms. So a group with
    several rows produces a RANGE and says it is unresolved - it does not
    quietly pick one.
  * **Some factors are not numbers.** Fixed seating and theatre screens
    carry "see_note_fixed_seating", because those are counted by seats, not
    by area. Computing with that string would be nonsense, so those rows
    are reported as not computable from area at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.engine.rules_loader import get_table2_occupant_load, group_letter_for_occupancy

# Industrial splits by hazard band rather than by sub-use, and the
# classifier already determines the band - so this is the one multi-row
# group that CAN be resolved automatically.
_INDUSTRIAL_BAND_TO_CODE = {
    "G-1": "G-1",
    "G-2": "G-2",
    "G-3": "G-3",
}


@dataclass(frozen=True)
class LoadFactor:
    """One Table 2 row, as this module needs it."""

    occupancy: str
    code: str
    factor: float | None
    basis: str
    """'net' or 'gross' - which floor area the factor is meant to divide."""
    note: str = ""


@dataclass
class OccupantLoad:
    """What Table 2 can say about this building, and what it cannot."""

    resolved: bool
    """Whether a single factor applies. False means the answer is a range."""

    people: int | None = None
    """The occupant load, rounded UP - a fraction of a person still needs
    somewhere to go."""

    low: int | None = None
    high: int | None = None
    """The range when several rows could apply."""

    area_sqm: float | None = None
    factors: list[LoadFactor] = field(default_factory=list)
    explanation: str = ""
    caveats: list[str] = field(default_factory=list)


def _rows_for(occupancy_type: str | None, hazard_band: str | None) -> list[LoadFactor]:
    if not occupancy_type:
        return []
    letter = group_letter_for_occupancy(occupancy_type)
    if letter is None:
        return []
    table = get_table2_occupant_load()
    rows = []
    for row in table.get("rows", []):
        code = str(row.get("occupancy_code", ""))
        # "E-II" and "G-1" hang off group letters E and G.
        if not (code == letter or code.startswith(f"{letter}-")):
            continue
        net, gross = row.get("net_factor"), row.get("gross_factor")
        raw = net if net is not None else gross
        basis = "net" if net is not None else "gross"
        rows.append(
            LoadFactor(
                occupancy=row.get("occupancy", ""),
                code=code,
                factor=float(raw) if isinstance(raw, (int, float)) else None,
                basis=basis,
                note="" if isinstance(raw, (int, float)) else str(raw),
            )
        )

    # Industrial: the hazard band the classifier already determined picks
    # the row, so this group does resolve.
    if letter == "G" and hazard_band:
        wanted = _INDUSTRIAL_BAND_TO_CODE.get(hazard_band.upper())
        if wanted:
            narrowed = [row for row in rows if row.code == wanted]
            if narrowed:
                return narrowed

    # A row coded with the bare group letter is the GENERAL case; a
    # hyphenated one (E-II datacentre, G-1 low hazard) is a subdivision
    # that only applies when that subdivision is known to apply. Without
    # this, an ordinary office was dragged into a 50-141 range by the
    # datacentre rows, when plain Business has a single factor of its own.
    general = [row for row in rows if row.code == letter]
    if general:
        return general
    return rows


def compute(
    occupancy_type: str | None,
    built_up_area_sqm: float | None,
    hazard_band: str | None = None,
) -> OccupantLoad | None:
    """The occupant load, or None when there is not enough to say anything.

    None rather than a zero or a guess: "we do not know" and "nobody is in
    this building" are different answers, and a compliance tool must not
    round the first into the second.
    """
    if not occupancy_type or not built_up_area_sqm or built_up_area_sqm <= 0:
        return None

    rows = _rows_for(occupancy_type, hazard_band)
    if not rows:
        return None

    computable = [row for row in rows if row.factor and row.factor > 0]
    caveats = [
        # Stated every time, because it is the difference between a figure
        # somebody can file and one they have to check.
        "Occupant load alone is not a pass or a fail. Turning it into a required exit "
        "width needs the stair and exit measurements in Table 3, which this Case File "
        "does not hold.",
        "Computed from the built-up area on this Case File. Table 2 distinguishes net "
        "floor area from gross; if the figure you entered is not the one the factor "
        "calls for, the result moves with it.",
    ]

    non_numeric = [row for row in rows if row.factor is None]
    if non_numeric and not computable:
        return OccupantLoad(
            resolved=False,
            area_sqm=built_up_area_sqm,
            factors=rows,
            explanation=(
                "Table 2 counts this occupancy by fixed seats, not by floor area, so an "
                "occupant load cannot be derived from area alone."
            ),
            caveats=caveats,
        )

    loads = sorted(math.ceil(built_up_area_sqm / row.factor) for row in computable)  # type: ignore[arg-type]

    if len(computable) == 1:
        row = computable[0]
        return OccupantLoad(
            resolved=True,
            people=loads[0],
            low=loads[0],
            high=loads[0],
            area_sqm=built_up_area_sqm,
            factors=computable,
            explanation=(
                f"{built_up_area_sqm:,.0f} m² ÷ {row.factor} m² per person "
                f"({row.basis} floor area, Table 2 “{row.occupancy}”) = {loads[0]} people, "
                "rounded up."
            ),
            caveats=caveats,
        )

    extra = ""
    if non_numeric:
        extra = (
            " One or more sub-uses in this group are counted by fixed seats rather than "
            "by area, and are not included in this range."
        )
    return OccupantLoad(
        resolved=False,
        low=loads[0],
        high=loads[-1],
        area_sqm=built_up_area_sqm,
        factors=rows,
        explanation=(
            f"Table 2 gives {len(computable)} different factors for this occupancy, "
            f"depending on the sub-use. At {built_up_area_sqm:,.0f} m² that is between "
            f"{loads[0]} and {loads[-1]} people. Which one applies depends on what the "
            "space is actually used for, which this Case File does not record." + extra
        ),
        caveats=caveats,
    )
