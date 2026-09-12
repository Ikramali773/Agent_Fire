"""Real embeddings-based (dense-vector, semantic) retrieval - the
§B.8-faithful counterpart to retriever.py's KeywordRetriever (BM25), which
was built instead of this as the *default* because this dev sandbox's
network policy blocks every embeddings-capable provider and Hugging Face
(verified directly - see backend/README.md's RAG section). This module is
the real thing, opt-in via FIRE_AGENT_RETRIEVER=embeddings
(app/knowledge/context.py), for use in an environment that can actually
reach the model.

Uses a local, free, open-weights model (sentence-transformers) rather than
a paid embeddings API - no per-call cost, no rate limit, consistent with
this project's Groq-first "avoid paid API costs" direction. The trade-off:
the model itself (~90 MB) has to be downloaded once from Hugging Face on
first use, which this dev sandbox cannot do (huggingface.co is blocked
here) - confirmed by testing, not assumed. A deployment with normal
internet access should be able to install `sentence-transformers` and use
this for real; that part specifically could not be verified live in this
sandbox, only the retrieval/ranking math below (tested with an injectable
fake encoder, see tests/test_knowledge_embedding_retriever.py).
"""

from __future__ import annotations

from typing import Protocol

from app.knowledge.corpus import Chunk, build_corpus
from app.knowledge.retriever import RetrievedChunk

_DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingBackendNotAvailableError(RuntimeError):
    """Mirrors LLMBackendNotConfiguredError's role for the LLM backends:
    raised when the real embedding encoder can't be constructed (package
    not installed, or the model weights can't be downloaded/loaded).
    Callers should catch this and fall back to KeywordRetriever rather than
    let it break Q&A retrieval entirely - see context.py's
    _default_retriever().
    """


class Encoder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEncoder:
    """The real encoder. Lazy-imports sentence_transformers so nothing else
    in this app needs it installed unless FIRE_AGENT_RETRIEVER=embeddings is
    actually set - same discipline as the Groq/Anthropic backends' lazy SDK
    imports in app/llm/backends/.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL_NAME):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingBackendNotAvailableError(
                "The 'sentence-transformers' package is not installed. Install it "
                "(pip install sentence-transformers) to use FIRE_AGENT_RETRIEVER=embeddings - "
                "not part of the default requirements.txt since it pulls in torch and is "
                "opt-in, not needed for the rest of the app."
            ) from exc
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as exc:  # first use downloads weights - network/disk/etc. can fail here
            raise EmbeddingBackendNotAvailableError(
                f"Could not load embedding model '{model_name}': {exc}"
            ) from exc

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(list(texts), convert_to_numpy=True).tolist()


def _cosine_similarities(query_vec: list[float], doc_vecs: list[list[float]]) -> list[float]:
    import numpy as np

    if not doc_vecs:
        return []
    query = np.asarray(query_vec, dtype=float)
    docs = np.asarray(doc_vecs, dtype=float)
    query_norm = np.linalg.norm(query)
    doc_norms = np.linalg.norm(docs, axis=1)
    denom = doc_norms * query_norm
    with np.errstate(invalid="ignore", divide="ignore"):
        sims = (docs @ query) / denom
    return np.nan_to_num(sims, nan=0.0).tolist()


class EmbeddingRetriever:
    """Encodes the entire corpus once at construction - it never changes at
    runtime, so there's no incremental-indexing concern, same as
    KeywordRetriever. `encoder` is injectable so the ranking math is fully
    testable without the real model (or even the sentence-transformers
    package) installed; production code gets a real SentenceTransformerEncoder
    by default.
    """

    def __init__(self, chunks: tuple[Chunk, ...] | None = None, encoder: Encoder | None = None):
        self._chunks = chunks if chunks is not None else build_corpus()
        self._encoder = encoder if encoder is not None else SentenceTransformerEncoder()
        self._embeddings = (
            self._encoder.encode([c.text for c in self._chunks]) if self._chunks else []
        )

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not query.strip() or not self._chunks:
            return []
        query_vec = self._encoder.encode([query])[0]
        sims = _cosine_similarities(query_vec, self._embeddings)
        ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:top_k]
        return [
            RetrievedChunk(chunk=self._chunks[i], score=sims[i]) for i in ranked if sims[i] > 0
        ]
