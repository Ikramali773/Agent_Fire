"""Tests app/ingest/pipeline.py's tier escalation end-to-end against real
PDFs/images and real Tesseract - only Tier 4 (vision-LLM) uses a fake, since
that's the one call that would otherwise need a real API key/network.
"""

import io

import pymupdf
from PIL import Image

from app.ingest.pipeline import run_pipeline
from app.llm.client import LLMClient, LLMNotConfiguredError


def make_text_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=14)
        y += 24
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_scanned_looking_pdf(lines: list[str]) -> bytes:
    """A PDF whose only content is a rasterized image of text (no native
    text layer) - simulates a scanned document, forcing the pipeline past
    Tier 1 into the OCR tiers.
    """
    text_pdf = make_text_pdf(lines)
    src = pymupdf.open(stream=text_pdf, filetype="pdf")
    pixmap = src[0].get_pixmap(dpi=200)
    src.close()

    doc = pymupdf.open()
    page = doc.new_page(width=pixmap.width, height=pixmap.height)
    page.insert_image(page.rect, pixmap=pixmap)
    out = doc.tobytes()
    doc.close()
    return out


class FakeVisionBackend:
    """Duck-types just enough of LLMBackend for Tier 4 to run without a
    real provider - see app/llm/client.py's testability design.
    """

    def generate_json_from_image(self, system, user_message, image_b64, media_type, json_schema, model):
        return {"page_text": "Vision tier read: Height 15 meters, Occupancy Residential"}


class NotConfiguredBackend:
    def generate_json_from_image(self, *args, **kwargs):
        raise LLMNotConfiguredError("no key")


class TestNativeTextPdf:
    def test_resolves_at_tier_1(self):
        pdf_bytes = make_text_pdf(["Fire Safety Plan", "Height: 32 meters", "State: Gujarat"])
        result = run_pipeline(pdf_bytes, "application/pdf")
        assert result.tier_used == 1
        assert result.needs_human_review is False
        assert "32 meters" in result.text
        assert result.page_count == 1


class TestScannedPdf:
    def test_falls_through_to_tier_2_ocr(self):
        pdf_bytes = make_scanned_looking_pdf(
            ["Fire Safety Plan", "Height: 18 meters", "Occupancy: Business", "State: Maharashtra"]
        )
        result = run_pipeline(pdf_bytes, "application/pdf")
        assert result.tier_used in (2, 3)  # OCR quality can push either way
        assert result.needs_human_review is False
        assert "18 meters" in result.text


class TestBlankOrUnreadablePdf:
    def test_blank_pdf_with_no_llm_falls_back_to_tier_3_needing_review(self):
        doc = pymupdf.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        result = run_pipeline(pdf_bytes, "application/pdf", llm=None)
        assert result.tier_used == 3
        assert result.needs_human_review is True
        assert result.failure_reason is not None

    def test_corrupted_file_fails_gracefully_not_crash(self):
        result = run_pipeline(b"this is not a real pdf file", "application/pdf")
        assert result.needs_human_review is True
        assert result.tier_used == 0
        assert "could not open" in result.failure_reason.lower()

    def test_unsupported_content_type(self):
        result = run_pipeline(b"whatever", "application/msword")
        assert result.needs_human_review is True
        assert result.tier_used == 0
        assert "unsupported" in result.failure_reason.lower()


class TestTier4VisionEscalation:
    def test_blank_page_with_configured_llm_escalates_to_vision(self):
        doc = pymupdf.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        llm = LLMClient(backend=FakeVisionBackend())
        result = run_pipeline(pdf_bytes, "application/pdf", llm=llm)

        assert result.tier_used == 4
        assert result.method == "vision_llm"
        assert result.needs_human_review is True  # Tier 4 always flagged for confirmation
        assert "Height 15 meters" in result.text

    def test_llm_not_configured_falls_back_to_tier_3_without_crashing(self):
        doc = pymupdf.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        llm = LLMClient(backend=NotConfiguredBackend())
        result = run_pipeline(pdf_bytes, "application/pdf", llm=llm)

        assert result.tier_used == 3
        assert result.needs_human_review is True


class TestImageUpload:
    def test_plain_image_file_resolves_via_ocr(self):
        pdf_bytes = make_text_pdf(["Number of exits: 4", "Number of staircases: 2"])
        src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pixmap = src[0].get_pixmap(dpi=200)
        src.close()
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        buf = io.BytesIO()
        image.save(buf, format="PNG")

        result = run_pipeline(buf.getvalue(), "image/png")
        assert result.tier_used in (2, 3)
        assert "exits" in result.text.lower()

    def test_corrupted_image_fails_gracefully(self):
        result = run_pipeline(b"not a real image", "image/png")
        assert result.needs_human_review is True
        assert result.tier_used == 0
