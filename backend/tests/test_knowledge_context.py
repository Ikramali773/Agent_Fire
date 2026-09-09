"""Tests for app/knowledge/context.py's build_qa_context() - the function
that combines the static summary (unchanged from before this pass) with
per-question retrieved passages (the new part). Uses a fake Retriever so
these don't depend on the real corpus's exact contents.
"""

from app.knowledge.context import build_qa_context, build_summary_context
from app.knowledge.corpus import Chunk
from app.knowledge.retriever import RetrievedChunk


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
