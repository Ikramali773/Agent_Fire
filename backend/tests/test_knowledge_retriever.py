"""Tests for app/knowledge/retriever.py's BM25 KeywordRetriever - a small
fixed fixture corpus for deterministic scoring assertions, plus one test
against the real digitized corpus to prove it retrieves something sane for
an actual question.
"""

from app.knowledge.corpus import Chunk
from app.knowledge.retriever import KeywordRetriever


def _fixture_chunks() -> tuple[Chunk, ...]:
    return (
        Chunk(
            chunk_id="a",
            text="High rise buildings above 24 metres require Annex D additional requirements.",
            citation="fixture:a",
        ),
        Chunk(
            chunk_id="b",
            text="Storage occupancy requires a wet riser and fire extinguishers per Table 7H.",
            citation="fixture:b",
        ),
        Chunk(
            chunk_id="c",
            text="Refuge areas are required on alternate floors for high rise buildings.",
            citation="fixture:c",
        ),
    )


class TestKeywordRetriever:
    def test_retrieves_most_relevant_chunk_first(self):
        retriever = KeywordRetriever(_fixture_chunks())
        results = retriever.retrieve("what applies to a storage building", top_k=3)
        assert results
        assert results[0].chunk.chunk_id == "b"

    def test_ranks_by_term_overlap(self):
        retriever = KeywordRetriever(_fixture_chunks())
        results = retriever.retrieve("high rise refuge area requirement", top_k=3)
        ids = [r.chunk.chunk_id for r in results]
        # "c" shares "high rise" and "refuge" - should outrank "a" (only
        # "high rise") and "b" (neither).
        assert ids[0] == "c"

    def test_no_matching_terms_returns_empty(self):
        retriever = KeywordRetriever(_fixture_chunks())
        assert retriever.retrieve("xylophone quokka nonsense", top_k=3) == []

    def test_empty_query_returns_empty(self):
        retriever = KeywordRetriever(_fixture_chunks())
        assert retriever.retrieve("", top_k=3) == []

    def test_empty_corpus_never_raises(self):
        retriever = KeywordRetriever(())
        assert retriever.retrieve("anything", top_k=3) == []

    def test_top_k_limits_results(self):
        retriever = KeywordRetriever(_fixture_chunks())
        results = retriever.retrieve("high rise buildings storage", top_k=1)
        assert len(results) == 1

    def test_real_corpus_answers_a_real_question(self):
        retriever = KeywordRetriever()  # default: the real digitized corpus
        results = retriever.retrieve("what is required for a high rise building", top_k=5)
        assert results
        assert any("high" in r.chunk.text.lower() for r in results)
