"""Tests for app/knowledge/context.py's build_qa_context() - the function
that combines the static summary (unchanged from before this pass) with
per-question retrieved passages (the new part). Uses a fake Retriever so
these don't depend on the real corpus's exact contents.
"""

from app.knowledge.context import _default_retriever, build_qa_context, build_summary_context
from app.knowledge.corpus import Chunk
from app.knowledge.retriever import KeywordRetriever, RetrievedChunk


class FakeRetriever:
    def __init__(self, results):
        self._results = results
        self.queries: list[str] = []

    def retrieve(self, query, top_k=5):
        self.queries.append(query)
        return self._results


def test_context_always_includes_the_static_summary():
    context = build_qa_context("some question", retriever=FakeRetriever([]))
    assert build_summary_context() in context


def test_context_appends_retrieved_chunks_with_citations():
    chunk = Chunk(chunk_id="x", text="Some retrieved fact.", citation="some_file.json (X)")
    retriever = FakeRetriever([RetrievedChunk(chunk=chunk, score=1.0)])

    context = build_qa_context("some question", retriever=retriever)

    assert "Some retrieved fact." in context
    assert "some_file.json (X)" in context
    assert retriever.queries == ["some question"]


def test_context_falls_back_to_summary_only_when_nothing_retrieved():
    context = build_qa_context("some question", retriever=FakeRetriever([]))
    assert context == build_summary_context()


class TestDefaultRetrieverSelection:
    def test_defaults_to_keyword_retriever(self, monkeypatch):
        monkeypatch.delenv("FIRE_AGENT_RETRIEVER", raising=False)
        _default_retriever.cache_clear()
        try:
            assert isinstance(_default_retriever(), KeywordRetriever)
        finally:
            _default_retriever.cache_clear()

    def test_embeddings_choice_falls_back_to_keyword_when_unavailable(self, monkeypatch):
        # Real negative-path coverage: sentence-transformers genuinely isn't
        # installed in this environment (see
        # test_knowledge_embedding_retriever.py), so this proves the actual
        # fallback fires rather than assuming it would.
        monkeypatch.setenv("FIRE_AGENT_RETRIEVER", "embeddings")
        _default_retriever.cache_clear()
        try:
            assert isinstance(_default_retriever(), KeywordRetriever)
        finally:
            _default_retriever.cache_clear()
