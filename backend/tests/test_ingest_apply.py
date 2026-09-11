"""Tests for app/ingest/apply.py's ingest_document() - the glue between the
OCR pipeline and fact extraction. Uses a real generated PDF (native text
layer, so Tier 1 handles it deterministically) and fake LLM backends, no
mocks of apply.py's own logic.
"""

import pymupdf

from app.ingest.apply import ingest_document
from app.llm.client import LLMClient, LLMUnavailableError
from app.models.case_file import CaseFile


def make_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=14)
        y += 24
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class RateLimitedBackend:
    """Duck-types a backend whose provider call raised a real rate-limit
    error - LLMClient._call() would already have translated that into
    LLMUnavailableError before extract_case_file_facts ever saw it, so
    faking it at that boundary (rather than constructing a real
    groq.RateLimitError here too - already covered in test_llm_client.py)
    keeps this test focused on apply.py's own handling of it.
    """

    def generate_json(self, system, user_message, json_schema, model):
        raise LLMUnavailableError("rate limited")


def test_rate_limited_llm_gives_a_distinct_message_from_not_configured():
    case_file = CaseFile(session_id="s1")
    pdf_bytes = make_pdf(["Fire NOC Certificate", "State: Gujarat", "City: Ahmedabad"])
    llm = LLMClient(backend=RateLimitedBackend())

    updated_case_file, summary = ingest_document(
        case_file, pdf_bytes, "application/pdf", "plan.pdf", llm
    )

    assert summary.tier_used == 1  # OCR itself succeeded (native text layer)
    assert summary.fields_extracted == []
    assert "temporarily rate-limited or unavailable" in summary.fact_extraction_skipped_reason
    assert "no LLM is configured" not in summary.fact_extraction_skipped_reason
    # The document is still recorded even though fact extraction didn't run.
    assert len(updated_case_file.source_documents) == 1
