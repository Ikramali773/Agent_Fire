"""Tests for app/knowledge/corpus.py's chunker - run against the real
digitized rule data (data/rules/**), not a fixture, so these fail loudly if
a future edit to that data breaks the chunker's assumptions.
"""

from app.knowledge.corpus import build_corpus


def test_corpus_is_nonempty_and_cached():
    chunks = build_corpus()
    assert len(chunks) > 100  # ~500 as of writing; a generous floor, not a pin
    assert build_corpus() is chunks  # lru_cache - same tuple object back


def test_every_chunk_has_a_citation_and_real_text():
    for chunk in build_corpus():
        assert chunk.text.strip()
        assert len(chunk.text) >= 15
        assert chunk.citation
        assert chunk.chunk_id


def test_table7_band_produces_a_labeled_chunk_with_installations():
    chunks = build_corpus()
    band_chunks = [c for c in chunks if "table7a_residential.json (HL-1)" in c.citation]
    assert band_chunks, "expected a chunk citing Table 7A's HL-1 band"
    assert any("installations" in c.text for c in band_chunks)
    assert any("condition" in c.text for c in band_chunks)


def test_readme_files_are_chunked_by_paragraph():
    chunks = build_corpus()
    readme_chunks = [c for c in chunks if c.citation.endswith("README.md")]
    assert readme_chunks
    assert any("NBCS 2026 Part F" in c.text for c in readme_chunks)


def test_internal_criteria_keys_are_not_chunked_standalone():
    # structured_criteria/match_any are engine plumbing, not human-readable
    # facts - see _SKIP_RECURSE_KEYS's docstring in corpus.py.
    chunks = build_corpus()
    assert not any("structured_criteria" in c.citation for c in chunks)
    assert not any("match_any" in c.citation for c in chunks)
