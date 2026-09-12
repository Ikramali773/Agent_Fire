"""Tests for app/knowledge/embedding_retriever.py.

The real SentenceTransformerEncoder cannot be exercised end-to-end in this
dev sandbox (huggingface.co is blocked by network policy - confirmed
directly, see backend/README.md's RAG section), so:
- The retrieval/ranking math (cosine similarity, top_k, empty-query/corpus
  handling) is tested for real via a small deterministic FakeEncoder -
  that's genuine test coverage, not mocked-out.
- SentenceTransformerEncoder's own construction is tested for the one thing
  actually verifiable here: that it fails with the documented, catchable
  EmbeddingBackendNotAvailableError (not an uncaught ImportError) when the
  package isn't installed - which is exactly the real state of this
  sandbox, not a simulated one.
"""

import pytest

from app.knowledge.corpus import Chunk
from app.knowledge.embedding_retriever import (
    EmbeddingBackendNotAvailableError,
    EmbeddingRetriever,
    SentenceTransformerEncoder,
)


class FakeEncoder:
    """Deterministic 2D "embeddings" so cosine similarity is easy to reason
    about by hand: vectors point in a small number of distinct directions,
    and a text's vector is chosen by which keyword it contains.
    """

    _VECTORS = {
        "fire": [1.0, 0.0],
        "storage": [0.0, 1.0],
        "neutral": [0.7, 0.7],
    }

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "fire" in lowered:
                vectors.append(self._VECTORS["fire"])
            elif "storage" in lowered:
                vectors.append(self._VECTORS["storage"])
            else:
                vectors.append(self._VECTORS["neutral"])
        return vectors


def _fixture_chunks() -> tuple[Chunk, ...]:
    return (
        Chunk(chunk_id="a", text="Fire extinguisher requirements", citation="fixture:a"),
        Chunk(chunk_id="b", text="Storage building area thresholds", citation="fixture:b"),
        Chunk(chunk_id="c", text="General building notes", citation="fixture:c"),
    )


class TestEmbeddingRetrieverRanking:
    def test_ranks_by_cosine_similarity_to_query(self):
        retriever = EmbeddingRetriever(chunks=_fixture_chunks(), encoder=FakeEncoder())

        results = retriever.retrieve("fire safety question", top_k=3)

        assert results[0].chunk.chunk_id == "a"  # exact direction match on "fire"
        assert results[0].score == pytest.approx(1.0, abs=1e-6)

    def test_different_query_ranks_different_chunk_first(self):
        retriever = EmbeddingRetriever(chunks=_fixture_chunks(), encoder=FakeEncoder())

        results = retriever.retrieve("storage capacity", top_k=3)

        assert results[0].chunk.chunk_id == "b"

    def test_top_k_limits_results(self):
        retriever = EmbeddingRetriever(chunks=_fixture_chunks(), encoder=FakeEncoder())
        results = retriever.retrieve("fire", top_k=1)
        assert len(results) == 1

    def test_empty_query_returns_empty(self):
        retriever = EmbeddingRetriever(chunks=_fixture_chunks(), encoder=FakeEncoder())
        assert retriever.retrieve("", top_k=3) == []

    def test_empty_corpus_never_raises(self):
        retriever = EmbeddingRetriever(chunks=(), encoder=FakeEncoder())
        assert retriever.retrieve("anything", top_k=3) == []

    def test_corpus_is_encoded_once_at_construction(self):
        calls = []
        chunks = _fixture_chunks()

        class CountingEncoder(FakeEncoder):
            def encode(self, texts):
                calls.append(len(texts))
                return super().encode(texts)

        retriever = EmbeddingRetriever(chunks=chunks, encoder=CountingEncoder())
        assert calls == [len(chunks)]  # corpus encoded once, at construction

        retriever.retrieve("fire", top_k=2)
        retriever.retrieve("storage", top_k=2)
        assert calls == [len(chunks), 1, 1]  # only the query gets re-encoded per call


class TestSentenceTransformerEncoderUnavailable:
    def test_raises_clear_error_when_package_not_installed(self):
        # Genuine negative-path coverage: sentence-transformers really is
        # not installed in this environment (it's an optional dependency,
        # see backend/README.md), so this exercises the real import-failure
        # path, not a simulated one.
        with pytest.raises(EmbeddingBackendNotAvailableError):
            SentenceTransformerEncoder()
