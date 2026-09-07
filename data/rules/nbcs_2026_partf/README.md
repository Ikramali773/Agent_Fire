# NBCS 2026 Part F — Structured Rule Data

Digitized from the source `.docx` (NBCS 2026 Part F, Fire and Life Safety, ~269 pp.) for use as the
Phase 1 classification engine's rule base (see `Fire_Safety_AI_Agent_Full_Scope_v3.md` §B.6).

## Status

This is a **first-pass digitization**, not a final production dataset. It was built by extracting
text/tables from the source `.docx` via XML parsing and manually structuring the result into JSON.
Every file that contains a table carries its own confidence notes; several — flagged
`"extraction_confidence": "needs_verification"` — have known ambiguities (merged cells, column
misalignment, or truncated OCR text in the source extraction) that should be checked against the
original document before this data drives a real compliance report. Do not treat a missing
verification pass as a blocker to development — build against this data, but track the flagged
items before shipping Phase 1's classification engine to real users.

## Files

| File | Contents | Confidence |
|---|---|---|
| `meta.json` | Edition info, and the verified Group H/J labeling correction | High — directly verified |
| `occupancy_groups.json` | Groups A–K with subdivisions, definitions, examples (clauses 3.1.1–3.1.11) | High |
| `applicability_thresholds.json` | Clause 1.2 height/area applicability table, high-rise flag (2.39), Note 2 single-staircase survivor rule | High |
| `table2_occupant_load.json` | Table 2 — occupant load factors | Medium — Business/Datacentre rows need re-check |
| `table3_capacity_factors.json` | Table 3 — exit width capacity factors | **Needs verification** — several occupancy rows (B, E, F, G, H) did not extract cleanly |
| `table4_travel_distance.json` | Table 4 — max travel distance by occupancy/construction type | High |
| `table7/table7a..7j_*.json` | Table 7A–7J — required firefighting installations per occupancy/size/height band | Medium-High — self-certification thresholds and R/NR grids extracted cleanly; a few "above X m" bands only say "see note" in the source and aren't tabulated |
| `table7k_7m_water_calc.json` | Table 7K/7M — water quantity/pump sizing per protection level code (CL-x / HL-x) | High |
| `table8_mains_sizing.json` | Table 8 — minimum main pipe sizes | High |
| `group_k_mixed_occupancy_separation.json` | Mixed-occupancy fire-separation rating matrix (clause 3.1.11) | High |
| `annex_b_hazard_classification.json` | Annex B — G-1/G-2/G-3 industrial hazard examples | **Needs verification** — 3-column table, cell-to-column mapping not individually re-checked |
| `annex_d_high_rise_summary.json` | Annex D — high-rise additional requirements (refuge areas, firefighting shafts, etc.) | High |
| `annex_m_performance_based_design.json` | Annex M — performance-based design scope and tenability criteria | High |
| `is_standards_referenced.json` | Referenced IS standards (product scope §C.5), verified against the source's List of Standards | High |

## Key facts worth remembering when building the classification engine (§B.6)

1. **Group H = Storage, Group J = Hazardous.** The document's own §3.1.1 summary list has these
   backwards. Always classify off the detailed clauses (3.1.9, 3.1.10) and the Table 7H/7J titles.
2. **Applicability is height OR area**, whichever is exceeded first — except Industrial G-1/G-2,
   which is area-only (any height, area > 2000 sqm).
3. **High-rise is a single flag** (`height_m >= 24`), not a tier — it stacks Annex D requirements on
   top of whatever the Table 7 lookup already produced.
4. **The single-staircase firefighting-shaft requirement (clause 1.2, Note 2) survives the
   applicability exemption** — it must still appear in a report for an otherwise out-of-scope
   building.
5. **Mixed Use (Group K) has no dedicated Table 7 letter.** Its zones are governed by the union of
   the component occupancies' Table 7 requirements, with the most restrictive occupancy governing
   each overlapping zone (clause 3.1.11.2).
6. **Performance-Based Design (Annex M) is scoped to heritage buildings** by default; extending it
   to any other building type requires state/local authority approval on a case-by-case basis, and
   must never be presented as a bypass of Table 7A–7J.

## Not yet digitized

Annex C (detailed fire-resistance-rating tables for individual construction materials — walls,
columns, beams, floors), Annex E (Atrium), Annex F (Data Centre detail beyond Table 7E), Annex G
(Car Parking detail), Annex H/J (Metro Stations/Trainways), Annex K (Industrial Venting), Annex N
(Specific Industries), Tables 9/10/11 (special-hazard detection/suppression selection), and the
full List of Standards (100+ entries) were read and spot-checked during review but not fully
structured into JSON — they matter more for later phases (geometry-aware compliance, specific
occupancy edge cases) than for the Phase 1 classification/report engine's core logic.
