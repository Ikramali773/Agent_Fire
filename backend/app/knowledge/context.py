"""Knowledge grounding for the Q&A side-branch (product scope B.3's
Code/Knowledge Agent), per the lightweight-RAG approach agreed for §B.8 (see
backend/README.md's RAG section for the full reasoning).

Two layers, concatenated by build_qa_context():
1. build_summary_context() - a short, static, hand-built summary of the
   handful of facts every question implicitly needs (occupancy groups,
   applicability thresholds, the high-rise flag, the single-staircase
   survivor rule). Kept small and manually verified rather than retrieved,
   since these are exactly the facts a wrong retrieval would be most costly
   to get wrong.
2. Retrieved chunks (over app/knowledge/corpus.py's chunked rule data) -
   real, citeable passages specific to THIS question. Two Retriever
   implementations exist (app/knowledge/retriever.py's Protocol): the
   default, KeywordRetriever (BM25, no dependencies, always works, chosen
   as the default because this dev sandbox's network policy blocks every
   embeddings-capable provider and Hugging Face - verified directly), and
   EmbeddingRetriever (app/knowledge/embedding_retriever.py, real semantic
   search via a local sentence-transformers model) - opt in with
   FIRE_AGENT_RETRIEVER=embeddings in an environment that can actually
   reach Hugging Face to download the model; falls back to KeywordRetriever
   automatically if it can't be constructed (package missing, model can't
   download), never crashing Q&A over a retrieval-backend problem.

answer_question()'s system prompt still instructs the model to say so
plainly when neither layer covers the question, rather than guessing a
clause number or threshold - the guardrail this module exists to serve
(§B.12) doesn't change just because retrieval got better.
"""

from __future__ import annotations

import os
from functools import lru_cache

from app.engine import rules_loader
from app.knowledge.retriever import KeywordRetriever, Retriever
from app.models.case_file import CaseFile


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
    if os.environ.get("FIRE_AGENT_RETRIEVER", "keyword") == "embeddings":
        try:
            from app.knowledge.embedding_retriever import EmbeddingRetriever

            return EmbeddingRetriever()
        except Exception:
            # Package not installed, model couldn't download (this dev
            # sandbox's network policy blocks huggingface.co - see module
            # docstring), out of memory, whatever the cause - Q&A retrieval
            # must never be the thing that breaks over an opt-in feature's
            # setup problem. Silent fallback, not a crash.
            pass
    return KeywordRetriever()


def build_case_file_context(case_file: CaseFile) -> str:
    """A compact summary of what's already known about the CURRENT case -
    fixes a real bug (caught in live browser testing) where the Q&A
    side-branch only ever saw static code-book material, so a question like
    "what's the area of the file I just uploaded" got answered as if no
    document had ever been uploaded, even though extraction had already
    populated the case file. Every line here just reflects a value the case
    file already has (from case_file.field_sources, or one of the
    document-only fields - see manager.py's _confirmation_summary, which
    shows the same data to the user), so this never tells the model
    anything beyond what the case file itself already says.
    """
    known: list[str] = []
    for name, source in case_file.field_sources.items():
        value = getattr(case_file, name, None)
        if value in (None, "", []):
            continue
        known.append(f"- {name}: {value} (source: {source.source.value})")

    if case_file.floor_wise_area:
        areas = "; ".join(f"{item.floor}: {item.area_sqm} sqm" for item in case_file.floor_wise_area)
        known.append(f"- floor_wise_area: {areas}")
    if case_file.kitchen_count is not None:
        known.append(f"- kitchen_count: {case_file.kitchen_count}")
    if case_file.door_count is not None:
        known.append(f"- door_count: {case_file.door_count}")
    if case_file.source_documents:
        docs = ", ".join(doc.filename for doc in case_file.source_documents)
        known.append(f"- documents already uploaded and read: {docs}")

    if not known:
        return ""

    lines = [
        "Known facts about the building/case currently being discussed - "
        "already captured from the user or an uploaded document. Use these "
        "directly to answer; never claim you cannot see an uploaded "
        "document's contents when a fact from it is listed here.",
        *known,
    ]

    result = case_file.classification_result
    if result.table_7_ref:
        lines.append(
            f"- classification: applies={result.applies}, table_7_ref={result.table_7_ref}, "
            f"protection_level={result.protection_level}"
        )

    return "\n".join(lines)


def build_qa_context(
    question: str,
    retriever: Retriever | None = None,
    top_k: int = 5,
    case_file: CaseFile | None = None,
) -> str:
    """The full context handed to answer_question(): the static summary
    above, this case's own known facts (if any), plus this question's own
    retrieved passages. Callers can inject a fake Retriever (tests do);
    real callers get the default BM25 one, built once and cached like the
    summary is.
    """
    retriever = retriever if retriever is not None else _default_retriever()
    context = build_summary_context()

    if case_file is not None:
        case_context = build_case_file_context(case_file)
        if case_context:
            context = f"{context}\n\n{case_context}"

    results = retriever.retrieve(question, top_k=top_k)
    if not results:
        return context

    lines = [context, "", "Retrieved reference passages for this specific question (cite these when relevant):"]
    for result in results:
        lines.append(f"- [{result.chunk.citation}] {result.chunk.text}")
    return "\n".join(lines)
