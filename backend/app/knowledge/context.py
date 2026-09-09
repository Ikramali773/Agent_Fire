"""Knowledge grounding for the Q&A side-branch (product scope B.3's
Code/Knowledge Agent), per the lightweight-RAG approach agreed for this pass
of §B.8 (see backend/README.md's RAG section for the full reasoning: real
embeddings-based retrieval needs a network path to an embeddings-capable
provider that this dev sandbox's network policy doesn't allow, verified
against Groq/OpenAI/Cohere/Voyage/Hugging Face).

Two layers, concatenated by build_qa_context():
1. build_summary_context() - a short, static, hand-built summary of the
   handful of facts every question implicitly needs (occupancy groups,
   applicability thresholds, the high-rise flag, the single-staircase
   survivor rule). Kept small and manually verified rather than retrieved,
   since these are exactly the facts a wrong retrieval would be most costly
   to get wrong.
2. Retrieved chunks (app/knowledge/retriever.py, over app/knowledge/
   corpus.py's chunked rule data) - real, citeable passages specific to
   THIS question, keyword-scored rather than embedded (see retriever.py's
   docstring for why). This is what makes this genuinely more than the old
   fixed fact-sheet: a question the static summary doesn't cover can still
   surface real source material instead of just "I don't have that."

answer_question()'s system prompt still instructs the model to say so
plainly when neither layer covers the question, rather than guessing a
clause number or threshold - the guardrail this module exists to serve
(§B.12) doesn't change just because retrieval got better.
"""

from __future__ import annotations

from functools import lru_cache

from app.engine import rules_loader
from app.knowledge.retriever import KeywordRetriever, Retriever


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


@lru_cache(maxsize=1)
def _default_retriever() -> Retriever:
    return KeywordRetriever()


def build_qa_context(question: str, retriever: Retriever | None = None, top_k: int = 5) -> str:
    """The full context handed to answer_question(): the static summary
    above, plus this question's own retrieved passages. Callers can inject a
    fake Retriever (tests do); real callers get the default BM25 one, built
    once and cached like the summary is.
    """
    retriever = retriever if retriever is not None else _default_retriever()
    context = build_summary_context()

    results = retriever.retrieve(question, top_k=top_k)
    if not results:
        return context

    lines = [context, "", "Retrieved reference passages for this specific question (cite these when relevant):"]
    for result in results:
        lines.append(f"- [{result.chunk.citation}] {result.chunk.text}")
    return "\n".join(lines)
