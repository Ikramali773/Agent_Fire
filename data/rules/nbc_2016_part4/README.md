# NBC 2016 Part 4 — Structured Rule Data (Legacy / Secondary Edition)

Digitized from the source `.docx` (National Building Code of India 2016, Part 4, Fire and Life
Safety, ~116 pp.) for use as the platform's **secondary/legacy** rule base, alongside the
primary/live NBCS 2026 Part F dataset at `../nbcs_2026_partf/`. See that dataset's README first if
you haven't already — this one assumes familiarity with the file layout and confidence-flagging
convention it established, and mirrors both as closely as the two source documents allow.

## Status

This is a **first-pass digitization**, not a final production dataset, and it should be treated as
**lower confidence than the 2026 dataset overall**. The reason is structural, not sloppiness: in
the 2026 source `.docx`, every table (including the large Table 7A–7J grids) survived as native,
editable Word tables. In this 2016 source `.docx`, the small tables (Table 1, 2, 3, 4, 5, 6, 8, 9)
are likewise native text — but the two largest and most operationally important tables, **Table 7
(Minimum Requirements for Firefighting Installations)** and **Annex B (industrial hazard
classification)**, are embedded as full-page **raster images** (a PDF-to-Word conversion artifact),
with no underlying text at all. Those two were recovered by running OCR (Tesseract) against the
page images and manually reconstructing structure from the OCR output. OCR of a dense, mostly-numeric,
many-merged-cell technical table is inherently error-prone — every row sourced this way carries an
explicit `extraction_confidence: "needs_verification"` flag and, where a specific cell's column
identity was ambiguous, the raw OCR token sequence is preserved rather than a guessed mapping.

**Do not treat a missing verification pass as a blocker to development** — this data is usable for
comparison/edition-detection logic today, but the Table 7 grid values in particular should be
checked against the original PDF page images before being used to generate an actual 2016-baseline
compliance report for a real building.

## Files

| File | Contents | Confidence |
|---|---|---|
| `meta.json` | Edition info, live-vs-legacy relationship to NBCS 2026, and the H/J labeling check | High — directly verified |
| `occupancy_groups.json` | Groups A–J (no K) with subdivisions, definitions, mixed-occupancy rule (3.1.12), Fire Zones concept | High — native text extraction |
| `applicability_thresholds.json` | Clause 1 (SCOPE) flat trigger-condition list, 15 m high-rise definition, Table 7 absolute height caps | High — native text extraction |
| `table_occupant_load.json` | Table 3 (2016's occupant-load table) | Medium — merged-cell reconstruction, same issue 2026's Table 2 has |
| `table_capacity_factors.json` | Table 4 (2016's exit-width capacity-factor table) | Medium — several rows blank/merged in extraction, same issue 2026's Table 3 has |
| `table_travel_distance.json` | Table 5 (2016's travel-distance table) plus a worked 2016-vs-2026 sprinkler-bonus comparison | High for the base figures; the 2016→2026 delta math is derived, not sourced directly |
| `table7_firefighting_installations/` | 2016's single unified Table 7, split into one file per occupancy (mirroring 2026's per-letter files) plus a shared `_columns_and_notes.json` | **Needs verification** — OCR'd from raster table images; see that folder's own confidence note |
| `annex_b_hazard_classification.json` | Annex B — Light/Moderate/High industrial hazard examples (2016's G-1/G-2/G-3 equivalent), plus a list of hazard categories 2026 added that 2016 lacks | **Needs verification** — OCR'd from raster page images, but content is a plain list (lower structural risk than Table 7's grid) |
| `is_standards_referenced.json` | Referenced IS standards, revision-by-revision compared against the 2026 dataset's own list | High — directly read from the native-text List of Standards section |
| `README.md` | This file | — |

## Key facts worth remembering — 2016 vs 2026 differences (the main deliverable of this task)

1. **No Group K "Mixed Use" in 2016 — confirmed.** 2016 defines exactly 9 groups (A–J, no I).
   Mixed occupancy exists only as a cross-cutting rule (clause 3.1.12): the **entire building** is
   governed by the **single most restrictive** component occupancy's requirements, with a flat
   **240 min** separation between differing occupancies. 2026's Group K, by contrast, is a directly
   selectable occupancy with its own applicability threshold (15 m / 1000 sqm) and a **per-zone**
   most-restrictive rule (clause 3.1.11.2) — a materially more granular mechanism. Note also that
   2016 has a **D-6** subdivision ("mixed assembly and mercantile occupancies", i.e. shopping malls)
   which is a *named subdivision of Group D*, not a general-purpose mixed-use mechanism — don't
   confuse it with Group K.

2. **The Group H/J summary-list labeling bug is 2026-only.** 2026's own clause 3.1.1 summary list
   mislabels H as "Hazardous" and J as "Storage" (backwards). **2016 has no such error** — its
   summary list and detailed clauses agree (H = Storage, J = Hazardous) everywhere checked,
   including Table 7's own section headers. This bug appears to have been introduced during the
   2026 drafting revision, not inherited from 2016.

3. **2016's applicability logic is a flat trigger list, not a per-occupancy height-OR-area table.**
   Clause 1 (SCOPE) says Part 4 applies if a building is high-rise (≥15 m, any occupancy) OR is a
   "special building" (hotel/educational/institutional/business/mercantile/industrial/storage/
   hazardous/mixed) with >500 sqm floor area on any floor OR is educational/institutional ≥9 m OR
   is **any** assembly building (Group D) **unconditionally**, no height/area floor at all, OR has
   >300 sqm incidental assembly, OR has ≥2 basements (or one >500 sqm). There is **no synthetic
   Low/Medium/High height-tier system** in 2016 either — that product-scope assumption doesn't
   describe 2016's actual mechanism, which was already a flat trigger list, just a much coarser and
   less occupancy-differentiated one than 2026's clean per-occupancy height/area table.

4. **High-rise threshold dropped from 15 m (2016) to a 24 m flag definition in 2026 conceptually,
   but note the two thresholds aren't doing identical jobs.** 2016's "High Rise Building" =
   ≥15 m, *irrespective of occupancy* (clause 2, Terminology) — and this 15 m figure is *also*
   2016's blanket applicability trigger (item 3 above). 2026 uses **24 m** for its high-rise flag
   (clause 2.39) but has its own, separate, occupancy-specific applicability table. A **15–24 m**
   building is "high rise" (Annex E treatment: firefighting shaft, refuge-area rules from 24 m up,
   biennial fire/life-safety audit) under 2016 but would **not** be flagged high-rise at all under
   2026 — this is probably the single most consequential number to get right when picking which
   edition governs a given building.

5. **2016 imposes hard occupancy-height CEILINGS that 2026 does not appear to carry.** Table 7's
   notes state buildings are **not permitted at all** above certain heights for specific occupancies:
   A-1/A-2 above 15 m; B/C/D/F above 30 m; G-1/G-2 above 18 m; G-3 above 15 m; H/J above 15 m; MLCP
   above 45 m. No equivalent "not permitted above height X" rule was found in the 2026 dataset for
   these occupancies — verify this is a genuine relaxation in 2026 rather than an artifact of what
   was digitized on the 2026 side.

6. **Table 7 travel-distance baselines are unchanged; the sprinkler bonus METHOD changed.** Every
   unsprinklered and Type-3/4 travel-distance figure in 2016's Table 5 is numerically identical to
   2026's Table 4. What changed is how the sprinkler bonus is computed: 2016 uses one flat **"+50%
   if fully sprinklered"** rule for every occupancy; 2026 publishes explicit per-occupancy
   sprinklered figures instead. Working the math out (see `table_travel_distance.json`'s
   `sprinklered_equivalent_comparison`) shows 2026 became **more generous** for Residential (+15 m),
   Business (+15 m), Industrial G-3 (+11.25 m), and dramatically more generous for Storage (+45 m,
   i.e. double) — but **more conservative** (shorter) for Industrial G-1/G-2 (−7.5 m) and Hazardous
   (−3.75 m). This is exactly the "Table 4 travel distances were updated in 2026" change flagged in
   the product scope doc, now quantified occupancy-by-occupancy.

7. **Table 7 itself: one unified table (2016) split into ten (2026).** 2016 has a single Table 7
   spanning all of Groups A–J across 11 landscape pages, with **14 columns per row** — the 8
   installation-type R/NR flags PLUS 4 water-storage/pump-capacity numeric columns folded directly
   into the same table (no separate water-calc table). 2026 splits this into Table 7A–7J (8 R/NR
   columns only) and moves the water/pump math into a *separate* Table 7K/7M keyed by an abstract
   protection-level code (HL-x/CL-x) that many different occupancy bands can share. This is a real
   methodology change, not just a cosmetic table split: 2026 decoupled "which installations does
   this band need" from "how much water/pump capacity does that combination require," letting the
   underlying water-quantity engineering be reused across occupancies. 2016 hard-codes a specific
   litre/lpm figure directly against every individual occupancy band. 2016's Table 7 also has **no
   dedicated PA/voice-evacuation column** at all (2026 gives this its own R/NR column across many
   occupancy bands) — in 2016, PA/talk-back is only a rider on the MOEFA requirement (Note 1) for a
   short, specific list of bands (certain A-5, C-1, D-1–D-5 bands, plus larger/multi-level car
   parking), a much narrower scope than 2026's broadly-applied PA/voice-evacuation requirement.

8. **Annex B's industrial hazard list grew substantially for 2026, largely to cover EV/lithium-ion
   and data-centre-adjacent occupancies.** 2016's Light/Moderate/High hazard lists map cleanly onto
   2026's G-1/G-2/G-3 lists for the vast majority of entries, but 2026 adds a distinct cluster of
   new categories with no 2016 counterpart: lithium-ion battery manufacturing/storage, EV-powered
   vehicle manufacturing, server rooms, MRI/scanning rooms, semiconductor and solar-cell
   manufacturing, and several "multiple block" cluster-building categories. See
   `annex_b_hazard_classification.json`'s `entries_present_in_2026_annex_b_but_not_found_in_2016`
   for the full list. This tracks with 2026's other new features noted elsewhere (Group K, E-II
   Datacentre sub-occupancy) — 2026's revision appears deliberately aimed at catching up with
   building types that were niche or nonexistent in 2016.

9. **IS standards: some unchanged, some many revisions behind.** IS 3844 (hydrants/hose reels,
   1989) and IS 4878 (cinema buildings, 1986) are cited **identically** in both editions — not
   everything changed. But IS 2189 (fire detection/alarm) jumps from the 2016-cited **2008 (fourth
   revision)** to **the 2026 code year itself**, and IS 2190 (portable extinguishers), IS 15105
   (sprinklers), IS 15325/15519/15493/12835 (spray/mist/gaseous/foam suppression) are all one to two
   decades newer in the 2026 citation list. Two of 2026's cited standards — IS 18271 (commercial
   kitchen guidelines) and IS 3614 (fire doors) — were **not found at all** in 2016's list; for
   commercial kitchens this is a genuine structural change (2016 has its own in-code Annex G for
   kitchens; 2026 apparently dropped that annex and defers to the external IS 18271 standard
   instead). IS 16700 (tall-building structural safety) and IS 4963 (accessibility) are new to 2026
   with no 2016 antecedent found, consistent with 2026's greater emphasis on tall buildings and
   accessibility.

10. **2016-only concepts not carried into this dataset's structure:** a city/area-level "Fire Zone"
    system (Fire Zone 1/2/3, restricting permitted construction types by occupancy hazard across a
    municipality) exists in 2016 (clauses 3.2.1–3.2.5) with no equivalent found in the 2026 material
    reviewed for this task — flagged in `occupancy_groups.json` but not otherwise modeled, since it
    governs land-use zoning rather than per-building classification.

## Not yet digitized

Annex A (calorific values — fully extracted as native text, but not built into its own JSON file
since it isn't in this task's required list), Annex C (fire-resistance-rating data tables 10–26 —
also raster-image-only in the source and not attempted here), Annex D (fire drill/evacuation
guidelines), Annex E (additional high-rise requirements — 2016's rough analogue of 2026's Annex D;
partially read during this pass and summarized inline in `applicability_thresholds.json` but not
built into its own file), Annex F (Atrium), Annex G (Commercial Kitchens — noteworthy because 2026
replaced its own equivalent annex with a reference to external standard IS 18271), Annex H (Car
Parking), Annex J/K (Metro Stations/Trainways — Table 7's own D-7 row explicitly defers here rather
than giving its own grid), Annex M (Fire Protection Considerations for Venting in Industrial
Buildings — note this is a *different topic* from 2026's Annex M, Performance-Based Design; 2016 has
**no** Performance-Based-Design annex or escape-hatch mechanism at all, another confirmed
edition difference), Table 1 (fire-resistance ratings by construction type), Table 2 (comparative
FAR by occupancy — read and summarized inline in occupancy_groups.json's Fire Zones note but not
built into its own file), Table 6 (staircase/lift-lobby pressurization), and the full List of
Standards (150+ entries — a broader, non-exhaustive capture is in `is_standards_referenced.json`).
These matter more for later phases than for the Phase 1 classification/report engine's core logic,
matching the same triage the 2026 dataset's README applied.
