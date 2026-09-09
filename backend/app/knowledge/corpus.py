"""Chunks the digitized rule corpus (data/rules/**) into small, citeable
text pieces - the real (if lightweight) implementation of §B.8's "chunk the
corpus" step. See app/knowledge/retriever.py for how a query finds the
right chunks among these, and app/knowledge/context.py for how they're
folded into a Q&A prompt.

This deliberately does NOT do embeddings/semantic chunking (see backend/
README.md's RAG section for why: no embeddings-capable provider is reachable
from this dev sandbox's network policy, verified against Groq, OpenAI,
Cohere, Voyage, and Hugging Face). What it does instead is generic and
structural: walk every JSON rule file's nested dicts/lists, and wherever a
dict contains enough of its own descriptive text (a condition, a title, a
table name, ...) to be worth retrieving on its own, emit it as one chunk
with a citation back to its source file (and, where the data has one, an
identifying label like a Table 7 band_id). This is intentionally the same
shape as a real chunk-then-embed pipeline would use - only the "then
embed" half is deferred; app/knowledge/retriever.py's Retriever Protocol is
what a real embeddings backend would plug into later without any of this
module changing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RULES_ROOT = _REPO_ROOT / "data" / "rules"

# Shorter strings are almost always codes/IDs ("A-I", "HL-3"), not prose
# worth retrieving as a standalone fact.
_MIN_TEXT_LEN = 15

# Internal engine plumbing, not human-readable facts - chunking these
# produces bare numeric fragments ("height_m_lt: 24") with no context about
# which band/table they belong to, so they're folded into their parent
# chunk's text (via _flatten_dict_to_text's nested-dict handling) instead of
# becoming chunks of their own.
_SKIP_RECURSE_KEYS = {"structured_criteria", "match_any"}

# Bounds how deep the walk goes below a file's root - the corpus is at most
# 3-4 levels deep by construction (file -> rows -> bands -> installations),
# so this is a safety cap against surprises in a future file shape, not a
# tuning knob that trims real content today.
_MAX_DEPTH = 6

_LABEL_KEYS = ("band_id", "occupancy", "table_name", "title", "subdivision_name", "state")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    citation: str


def _is_flat_scalar_dict(d: dict) -> bool:
    return all(not isinstance(v, (dict, list)) for v in d.values())


def _flatten_dict_to_text(d: dict) -> str:
    parts = []
    for key, value in d.items():
        if isinstance(value, str) and len(value) >= _MIN_TEXT_LEN:
            parts.append(f"{key}: {value}")
        elif isinstance(value, (int, float, bool)):
            parts.append(f"{key}: {value}")
        elif isinstance(value, dict) and _is_flat_scalar_dict(value):
            nested = ", ".join(f"{k}={v}" for k, v in value.items())
            if nested:
                parts.append(f"{key}: {nested}")
    return "; ".join(parts)


def _identifying_label(d: dict) -> str | None:
    for key in _LABEL_KEYS:
        value = d.get(key)
        if isinstance(value, str):
            return value
    return None


def _walk_json(node, path: list[str], filename: str, depth: int, chunks: list[Chunk]) -> None:
    if depth > _MAX_DEPTH:
        return

    if isinstance(node, dict):
        text = _flatten_dict_to_text(node)
        if text and len(text) >= _MIN_TEXT_LEN:
            label = _identifying_label(node)
            location = "/".join(path)
            citation = filename
            if label:
                citation += f" ({label})"
            elif location:
                citation += f" [{location}]"
            chunks.append(
                Chunk(chunk_id=f"{filename}:{location or 'root'}:{len(chunks)}", text=text, citation=citation)
            )
        for key, value in node.items():
            if key in _SKIP_RECURSE_KEYS:
                continue
            if isinstance(value, dict) and not _is_flat_scalar_dict(value):
                _walk_json(value, path + [key], filename, depth + 1, chunks)
            elif isinstance(value, list):
                _walk_json(value, path + [key], filename, depth + 1, chunks)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, path, filename, depth + 1, chunks)


def _chunk_readme(path: Path) -> list[Chunk]:
    rel = path.relative_to(_RULES_ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    chunks = []
    for i, para in enumerate(part.strip() for part in text.split("\n\n")):
        para = " ".join(para.split())  # collapse markdown line-wrapping into one line
        if len(para) >= _MIN_TEXT_LEN:
            chunks.append(Chunk(chunk_id=f"{rel}:para{i}", text=para, citation=rel))
    return chunks


@lru_cache(maxsize=1)
def build_corpus() -> tuple[Chunk, ...]:
    """The full chunked corpus, computed once per process (the source files
    are static at runtime - there's no ingestion pipeline to re-run here).
    """
    chunks: list[Chunk] = []

    for json_path in sorted(_RULES_ROOT.rglob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rel = json_path.relative_to(_RULES_ROOT).as_posix()
        _walk_json(data, [], rel, 0, chunks)

    for md_path in sorted(_RULES_ROOT.rglob("README.md")):
        chunks.extend(_chunk_readme(md_path))

    return tuple(chunks)
