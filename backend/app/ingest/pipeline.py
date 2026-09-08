"""Fail-safe document ingest pipeline - product scope §B.7.

Orchestrates the tiered escalation (§B.7.1): try each tier in order, stop as
soon as one clears its confidence threshold, and record which tier actually
resolved the upload (§B.7.2's instrumentation requirement - "log which tier
resolved each upload... review it regularly to see what fraction of real
uploads are forcing expensive Tier 4 calls").

Tier 5 (human-in-the-loop) is NOT code here - per §B.7.1 it's "ask the user
directly, show the page image." That's what already happens automatically:
run_pipeline never invents a value, so a field the pipeline couldn't extract
with confidence just stays unfilled, and the existing dialogue manager
(app/dialogue/) asks for it normally on the next conversation turn. No
special ingest-side code needed for Tier 5 to "work."

Escalates through:
  Tier 1 - direct PDF text-layer extraction (tiers.py, no OCR at all;
           images obviously skip straight to Tier 2)
  Tier 2 - OCR on the rendered page images
  Tier 3 - OCR again after deskew/denoise/binarize/upscale preprocessing
  Tier 4 - vision-LLM direct read (only if an LLM is configured; skipped
           with a clear reason otherwise, never a crash)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

import pymupdf
from PIL import Image, UnidentifiedImageError

from app.ingest import tiers
from app.llm.client import LLMClient, LLMNotConfiguredError

# Formats this pipeline actually knows how to open. Multi-file bundles,
# non-English/regional-language text, and formats beyond these are
# explicitly out of scope for Phase 1 (§B.7.3 lists them as decisions to
# make explicitly, not silently support or silently fail on).
_SUPPORTED_PDF_TYPES = {"application/pdf"}
_SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg"}

# Vision-LLM confidence isn't self-reported yet (§B.7.2 suggests prompting
# for per-field certainty and treating hedging language as low confidence -
# deferred, see README) - this fixed value just needs to sit below every
# programmatic auto-accept threshold so Tier 4 results are always routed to
# human confirmation, never silently trusted the way Tiers 1-3 are once they
# clear their own thresholds.
TIER4_CONFIDENCE = 70.0


@dataclass
class IngestResult:
    text: str
    tier_used: int
    confidence: float
    method: str
    page_count: int
    needs_human_review: bool
    failure_reason: str | None = None
    page_images: list[bytes] = field(default_factory=list)  # PNG bytes, only kept when Tier 4 was attempted


def _is_probably_corrupt(exc: Exception) -> bool:
    # pymupdf raises a plain Exception/RuntimeError with no dedicated type to
    # catch narrowly, so this is a best-effort classification used only to
    # phrase the failure_reason message; the caller's behavior (return
    # needs_human_review) is the same either way. Message text confirmed
    # against a real invalid-PDF-bytes input while writing the tests for
    # this function - "failed to open stream" is what pymupdf actually
    # raises, not a guessed string.
    message = str(exc).lower()
    return any(
        phrase in message
        for phrase in ("cannot open", "syntax error", "format error", "failed to open")
    )


def _image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _escalate_from_ocr(images: list[Image.Image], page_count: int, llm: LLMClient | None) -> IngestResult:
    """Shared Tier 2 -> Tier 3 -> Tier 4 escalation, used by both the PDF
    path (after Tier 1 was skipped/insufficient) and the plain-image path
    (which has no text layer to try Tier 1 against at all).
    """
    tier2 = tiers.ocr_standard(images)
    if tier2.confidence >= tiers.TIER2_MIN_CONFIDENCE:
        return IngestResult(
            text=tier2.text, tier_used=2, confidence=tier2.confidence, method=tier2.method,
            page_count=page_count, needs_human_review=False,
        )

    tier3 = tiers.ocr_with_preprocessing(images)
    if tier3.confidence >= tiers.TIER3_MIN_CONFIDENCE:
        return IngestResult(
            text=tier3.text, tier_used=3, confidence=tier3.confidence, method=tier3.method,
            page_count=page_count, needs_human_review=False,
        )

    page_png_bytes = [_image_to_png_bytes(img) for img in images]

    # Tier 4: only attempted if an LLM is actually configured - this is the
    # expensive, paid-per-page tier (§B.7.1), so "not configured" must never
    # silently degrade into "pretend it succeeded" or a crash; it just means
    # Tier 3's best-effort result is what we have, flagged for human review.
    if llm is not None:
        try:
            from app.ingest.vision import run_vision_tier

            tier4_text = run_vision_tier(page_png_bytes, llm)
            if tier4_text.strip():
                return IngestResult(
                    text=tier4_text, tier_used=4, confidence=TIER4_CONFIDENCE, method="vision_llm",
                    page_count=page_count, needs_human_review=True,
                )
        except LLMNotConfiguredError:
            pass

    return IngestResult(
        text=tier3.text, tier_used=3, confidence=tier3.confidence, method=tier3.method,
        page_count=page_count, needs_human_review=True,
        failure_reason="Low-confidence extraction - please confirm the details in chat.",
        page_images=page_png_bytes,
    )


def run_pipeline(file_bytes: bytes, content_type: str, llm: LLMClient | None = None) -> IngestResult:
    if content_type in _SUPPORTED_IMAGE_TYPES:
        try:
            image = Image.open(BytesIO(file_bytes))
            image.load()
        except UnidentifiedImageError:
            return IngestResult(
                text="", tier_used=0, confidence=0.0, method="failed", page_count=0,
                needs_human_review=True,
                failure_reason="Could not read this image file - it may be corrupted or an unsupported format.",
            )
        return _escalate_from_ocr([image], page_count=1, llm=llm)

    if content_type not in _SUPPORTED_PDF_TYPES:
        return IngestResult(
            text="", tier_used=0, confidence=0.0, method="unsupported", page_count=0,
            needs_human_review=True,
            failure_reason=(
                f"Unsupported file type '{content_type}'. This pipeline reads PDF, PNG, and JPEG "
                "only - multi-format bundles and other document types are out of scope for Phase 1."
            ),
        )

    try:
        tier1 = tiers.extract_text_layer(file_bytes)
        page_count = _count_pdf_pages(file_bytes)
    except Exception as exc:  # noqa: BLE001 - corrupt/unreadable file must never crash the request
        return IngestResult(
            text="", tier_used=0, confidence=0.0, method="failed", page_count=0,
            needs_human_review=True,
            failure_reason=(
                "Could not open this file - it may be corrupted or not a valid PDF."
                if _is_probably_corrupt(exc)
                else f"Unexpected error reading the file: {exc}"
            ),
        )

    # extract_text_layer already applies TIER1_MIN_TEXT_LENGTH internally and
    # reports confidence as either 95.0 (enough native text) or 0.0 (not) -
    # so the check here is just "did tier 1 clear its own bar", not another
    # length comparison.
    if tier1.confidence > 0:
        return IngestResult(
            text=tier1.text, tier_used=1, confidence=tier1.confidence, method=tier1.method,
            page_count=page_count, needs_human_review=False,
        )

    images = tiers.render_pdf_pages(file_bytes)
    return _escalate_from_ocr(images, page_count=page_count, llm=llm)


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()
