"""Lightweight knowledge grounding for the Q&A side-branch (product scope B.3's
Code/Knowledge Agent) - NOT the full RAG system described in §B.8.

§B.8 calls for chunking the whole NBCS 2026 + NBC 2016 corpus by clause,
embedding it, and retrieving by metadata-filtered similarity search. That is
a separate, larger build (vector store choice, ingestion pipeline, retrieval
tuning) that hasn't been started yet. What this module does instead: builds a
short, static summary from the already-digitized rule data
(data/rules/nbcs_2026_partf/) and hands it to the LLM as its only grounding.

This means Q&A answers are reliable for the facts that summary actually
contains (occupancy classification, applicability thresholds, high-rise
flag) and will correctly say "I don't have that in my reference material" for
anything else - which is the honest, safe behavior until real RAG exists.
Do not expand this into a bigger hand-written blob as a substitute for
building retrieval; that doesn't scale past a handful of facts and produces
exactly the false-confidence failure mode B.8's guardrails exist to prevent.
"""

from __future__ import annotations

from functools import lru_cache

from app.engine import rules_loader


@lru_cache(maxsize=1)
def build_summary_context() -> str:
    meta = rules_loader.get_meta()
    thresholds = rules_loader.get_applicability_thresholds()

    lines = [
        f"Primary code edition: NBCS {meta['code_edition']} Part F. "
        f"{meta['legacy_reference_note']}",
        "",
        "Occupancy groups: A Residential, B Educational, C Institutional, "
        "D Assembly, E Business, F Mercantile, G Industrial (subdivided "
        "G-1 low / G-2 moderate / G-3 high hazard), H Storage, J Hazardous, "
        "K Mixed Use.",
        (
            f"IMPORTANT: {meta['known_source_document_inconsistency']['resolution']} "
            "(the code's own summary list has H and J backwards)."
        ),
        "",
        "Applicability thresholds (clause 1.2) - Part F applies if EITHER "
        "height OR floor area is exceeded (Industrial G-1/G-2 is area-only):",
    ]
    for row in thresholds["thresholds"]:
        height = f"{row['height_m']} m" if row["height_m"] is not None else "any height"
        lines.append(f"- {row['occupancy']}: {height} / {row['floor_area_sqm']} sqm")

    lines.append("")
    lines.append(
        "High-rise flag (clause 2.39): is_high_rise = height_m >= 24, "
        "occupancy-independent, triggers Annex D on top of the base "
        "Table 7 requirements."
    )
    lines.append(
        "Single-staircase survivor rule (clause 1.2, Note 2): even a building "
        "below the applicability threshold with only one staircase must still "
        "provide a firefighting-shaft-type staircase with a ventilated lobby "
        "and stairwell, a 2 h fire door for the lobby, and a 1 h fire door "
        "for the stairwell."
    )

    return "\n".join(lines)
