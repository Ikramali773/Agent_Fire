"""Tests for app/knowledge/context.py's build_qa_context() - the function
that combines the static summary (unchanged from before this pass) with
per-question retrieved passages (the new part). Uses a fake Retriever so
these don't depend on the real corpus's exact contents.
"""

import uuid

from app.knowledge.context import (
    _default_retriever,
    build_case_file_context,
    build_qa_context,
    build_summary_context,
)
from app.knowledge.corpus import Chunk
from app.knowledge.retriever import KeywordRetriever, RetrievedChunk
from app.models.case_file import CaseFile, FieldSource, FieldSourceKind


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


class TestCaseFileContext:
    """Regression coverage for a live-tested bug: a question about a
    just-uploaded document was answered as if nothing had been uploaded,
    because the Q&A side-branch never saw the case file's own facts - only
    the static code-book summary. See manager.py's _safe_answer_question.
    """

    def _case_file(self) -> CaseFile:
        return CaseFile(session_id=str(uuid.uuid4()))

    def test_empty_case_file_yields_no_context(self):
        assert build_case_file_context(self._case_file()) == ""

    def test_document_extracted_field_appears_with_its_source(self):
        case_file = self._case_file()
        case_file.built_up_area_sqm = 2879.75
        case_file.field_sources["built_up_area_sqm"] = FieldSource(
            value=2879.75, source=FieldSourceKind.DOCUMENT, confidence=0.63
        )

        context = build_case_file_context(case_file)

        assert "built_up_area_sqm: 2879.75" in context
        assert "source: document" in context

    def test_document_only_fields_appear_even_without_a_field_source(self):
        # floor_wise_area/kitchen_count/door_count have no intake node and so
        # never get a field_sources entry (see manager.py's
        # _confirmation_summary) - they must still surface here.
        case_file = self._case_file()
        case_file.kitchen_count = 1
        case_file.door_count = 12

        context = build_case_file_context(case_file)

        assert "kitchen_count: 1" in context
        assert "door_count: 12" in context

    def test_uploaded_document_filenames_appear(self):
        from app.models.case_file import SourceDocument

        case_file = self._case_file()
        case_file.source_documents = [
            SourceDocument(filename="Site Plan Drawing (2).pdf", pages=1, overall_confidence=0.63)
        ]

        context = build_case_file_context(case_file)

        assert "Site Plan Drawing (2).pdf" in context

    def test_build_qa_context_includes_case_file_facts_alongside_static_summary(self):
        case_file = self._case_file()
        case_file.built_up_area_sqm = 2879.75
        case_file.field_sources["built_up_area_sqm"] = FieldSource(
            value=2879.75, source=FieldSourceKind.DOCUMENT, confidence=0.63
        )

        context = build_qa_context("what is the area?", retriever=FakeRetriever([]), case_file=case_file)

        assert build_summary_context() in context
        assert "built_up_area_sqm: 2879.75" in context

    def test_build_qa_context_omits_case_file_block_when_nothing_known(self):
        context = build_qa_context(
            "some question", retriever=FakeRetriever([]), case_file=self._case_file()
        )
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
