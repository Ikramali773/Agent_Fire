"""Pluggable retrieval interface for the Q&A side-branch (§B.8).

Retriever is a Protocol - mirrors the LLMBackend pattern in app/llm/ - so a
real embeddings-based implementation (once this deployment has network
access to an embeddings-capable provider; see backend/README.md's RAG
section for why that isn't available in this dev sandbox - Groq, OpenAI,
Cohere, Voyage, and Hugging Face were all checked and are unreachable here)
can be dropped in later without app/knowledge/context.py or
app/dialogue/manager.py changing at all.

KeywordRetriever is the only implementation today: a small hand-rolled BM25
scorer (no external dependency - pip installs in this sandbox are flaky
against PyPI's file host, and BM25 is ~30 lines) over
app/knowledge/corpus.py's chunks. It's deterministic, needs no network call,
and is fully unit-testable, unlike an embeddings call would be here.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from app.knowledge.corpus import Chunk, build_corpus

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_BM25_K1 = 1.5
_BM25_B = 0.75


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]: ...


class KeywordRetriever:
    """BM25 (Okapi) over a fixed corpus, indexed once at construction - the
    source data is static at runtime, so there's no incremental-indexing
    concern to design for.
    """

    def __init__(self, chunks: tuple[Chunk, ...] | None = None):
        self._chunks = chunks if chunks is not None else build_corpus()
        self._doc_tokens = [_tokenize(c.text) for c in self._chunks]
        self._doc_len = [len(toks) for toks in self._doc_tokens]
        self._avg_len = (sum(self._doc_len) / len(self._doc_len)) if self._doc_len else 0.0
        self._doc_term_counts = [Counter(toks) for toks in self._doc_tokens]
        self._df: Counter[str] = Counter()
        for toks in self._doc_tokens:
            for term in set(toks):
                self._df[term] += 1
        self._n_docs = len(self._chunks)

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        # Standard BM25 idf, floored at 0 so a term appearing in most/all
        # documents contributes nothing rather than a negative weight that
        # would let it subtract from an otherwise-relevant chunk's score.
        return max(0.0, math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1e-9))

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        query_terms = set(_tokenize(query))
        if not query_terms or not self._chunks:
            return []

        scored: list[tuple[float, int]] = []
        for i, term_counts in enumerate(self._doc_term_counts):
            score = 0.0
            doc_len = self._doc_len[i]
            for term in query_terms:
                tf = term_counts.get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf(term)
                denom = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * doc_len / (self._avg_len or 1))
                score += idf * (tf * (_BM25_K1 + 1)) / denom
            if score > 0:
                scored.append((score, i))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [RetrievedChunk(chunk=self._chunks[i], score=score) for score, i in scored[:top_k]]
