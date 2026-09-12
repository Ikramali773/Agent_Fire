"""Tiers 1-3 of the fail-safe OCR pipeline (product scope §B.7.1). Tier 4
(vision-LLM) lives in vision.py since it needs the LLM layer; Tier 5
(human-in-the-loop) isn't code at all - see pipeline.py's docstring.

Every function here is pure/deterministic given its input image or PDF bytes
- no LLM calls, so this whole module is testable with zero network access
and no API key, same discipline as app/engine/classifier.py.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pymupdf
import pytesseract
from PIL import Image, ImageFilter, ImageOps

# Escalation thresholds (product scope §B.7.2: "implement as explicit code,
# not agent judgment, so the cost-control behavior is predictable and
# testable"). Tuned conservatively - re-tune against real scanned documents
# per §B.11 research item 2; these are reasonable starting points, not
# validated against a real sample corpus.
TIER1_MIN_TEXT_LENGTH = 40  # chars; below this, treat the "text layer" as too sparse to trust
TIER2_MIN_CONFIDENCE = 60.0  # pytesseract's 0-100 scale
TIER3_MIN_CONFIDENCE = 60.0

RENDER_DPI = 200  # rasterization resolution for OCR tiers


@dataclass
class TierResult:
    tier: int
    text: str
    confidence: float  # 0-100 scale throughout, including tier 1 (heuristic)
    method: str


def _extract_tables_as_text(page: pymupdf.Page) -> str:
    """Architectural drawing sheets (plans, elevations) commonly carry a
    ruled-line schedule table somewhere on the page - an area statement
    (floor-wise breakdown), a door schedule, a title block. page.get_text()
    alone flattens the whole page in roughly left-to-right/top-to-bottom
    reading order, which scrambles a table's rows/columns together with
    whatever else is drawn around it (dimension labels, notes, the drawing
    itself) into word soup an LLM can't reliably map back to fields.
    find_tables() instead uses the page's own ruling lines to recover the
    actual row/column structure, so a table gets handed to the LLM as
    genuine rows rather than scrambled text. Only works for a vector
    (ruled-line) table in a native-text PDF - Tiers 2/3's OCR path has no
    equivalent bounding-box table reconstruction yet, a known gap for
    scanned/rasterized drawings.
    """
    try:
        tables = page.find_tables()
    except Exception:
        return ""
    blocks = []
    for table in tables.tables:
        try:
            rows = table.extract()
        except Exception:
            continue
        if not rows:
            continue
        lines = [" | ".join("" if cell is None else str(cell) for cell in row) for row in rows]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def extract_text_layer(pdf_bytes: bytes) -> TierResult:
    """Tier 1: direct text-layer extraction. Confidence is a heuristic, not
    a real per-character score - native PDF text is either there and
    trustworthy or it isn't, so this just distinguishes "enough text to be
    real content" from "too little, probably a scanned image PDF."
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages_text = []
        for page in doc:
            page_text = page.get_text()
            table_text = _extract_tables_as_text(page)
            if table_text:
                page_text = f"{page_text}\n\n[Table(s) detected on this page]\n{table_text}"
            pages_text.append(page_text)
    finally:
        doc.close()
    text = "\n\n".join(pages_text).strip()
    confidence = 95.0 if len(text) >= TIER1_MIN_TEXT_LENGTH else 0.0
    return TierResult(tier=1, text=text, confidence=confidence, method="text_layer")


def render_pdf_pages(pdf_bytes: bytes, dpi: int = RENDER_DPI) -> list[Image.Image]:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        images = []
        for page in doc:
            pixmap = page.get_pixmap(dpi=dpi)
            images.append(Image.open(io.BytesIO(pixmap.tobytes("png"))))
        return images
    finally:
        doc.close()


def _fix_orientation(image: Image.Image) -> Image.Image:
    """Failure mode from §B.7.3: rotated/upside-down scans. pytesseract's
    orientation-and-script-detection (OSD) reports the rotation needed to
    make the text upright; silently skip correction if OSD can't find
    enough text to make a determination rather than raising. This is a real,
    observed limitation, not a hypothetical edge case - OSD needs several
    lines of text to detect rotation reliably; a page with only a line or
    two of text (sparse title blocks, short labels) will often not get
    auto-rotated, and rotation correction should not be assumed to always
    fire just because a page happens to be upside down.
    """
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        rotation = osd.get("rotate", 0)
        if rotation:
            return image.rotate(-rotation, expand=True)
    except pytesseract.TesseractError:
        pass
    return image


# Confirmed via direct testing (not a guess): Tesseract's default full-page
# layout analysis (PSM 3, what image_to_data/image_to_string use with no
# config override) can return NOTHING for a ruled-line/bordered table - it
# misclassifies the bordered region as a non-text layout element rather
# than running OCR inside it - while "--psm 11" (sparse text, no page
# layout assumptions) recovers at least partial words from the same region.
# A rasterized architectural drawing's area-statement or door-schedule box
# is exactly this shape, so Tiers 2/3 ran a real risk of silently dropping
# it entirely, not just reading it poorly.
_SPARSE_TEXT_PSM_CONFIG = "--psm 11"


def _ocr_sparse_text(image: Image.Image) -> str:
    """Supplementary OCR pass for content the primary pass misses entirely
    (see module comment above). This does NOT reconstruct row/column
    structure the way Tier 1's find_tables() does for native-text PDFs -
    it's a best-effort "don't lose it completely" fallback for scanned/
    photographed drawings, merged in by _merge_sparse_text() and tagged
    distinctly so the LLM (and a human reviewer) can tell it's a lower-
    confidence supplementary read, not the primary transcription.
    """
    try:
        return pytesseract.image_to_string(image, config=_SPARSE_TEXT_PSM_CONFIG).strip()
    except pytesseract.TesseractError:
        return ""


def _merge_sparse_text(primary_text: str, sparse_text: str) -> str:
    if not sparse_text:
        return primary_text
    primary_words = set(primary_text.lower().split())
    new_words = [w for w in sparse_text.split() if w.lower() not in primary_words]
    # Only worth appending if the sparse pass actually found content the
    # primary pass didn't - otherwise it's just re-finding (usually less
    # accurately) what's already there, adding noise instead of value.
    if len(new_words) < 2:
        return primary_text
    tag = "[Additional text detected via sparse-text OCR - may include a table/schedule the main pass missed]"
    return f"{primary_text}\n\n{tag}\n{sparse_text}" if primary_text else f"{tag}\n{sparse_text}"


def _ocr_with_confidence(image: Image.Image) -> tuple[str, float]:
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = []
    confidences = []
    for text, conf in zip(data["text"], data["conf"]):
        conf = float(conf)
        if text.strip() and conf >= 0:
            words.append(text)
            confidences.append(conf)
    joined_text = " ".join(words)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return joined_text, avg_confidence


def ocr_standard(images: list[Image.Image]) -> TierResult:
    """Tier 2: OCR on rendered page images, no preprocessing beyond
    orientation correction (cheap enough to always apply, not really a
    "tier 3" step).
    """
    texts = []
    confidences = []
    for image in images:
        image = _fix_orientation(image)
        text, confidence = _ocr_with_confidence(image)
        text = _merge_sparse_text(text, _ocr_sparse_text(image))
        texts.append(text)
        confidences.append(confidence)
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return TierResult(
        tier=2, text="\n\n".join(texts), confidence=overall_confidence, method="ocr_standard"
    )


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Tier 3 preprocessing (§B.7.2): deskew is NOT implemented (needs
    OpenCV or a Hough-transform equivalent - deferred, see module docstring
    in pipeline.py's "not built" note) - denoise/binarize/upscale are, using
    only Pillow so this pipeline has no extra system dependency beyond
    Tesseract itself.
    """
    grayscale = ImageOps.grayscale(image)
    # Upscale small/low-DPI scans - OCR accuracy drops sharply below ~150 DPI
    # equivalent; doubling a small image gives Tesseract more pixels to work with.
    if grayscale.width < 1500:
        scale = 1500 / grayscale.width
        grayscale = grayscale.resize(
            (int(grayscale.width * scale), int(grayscale.height * scale)), Image.LANCZOS
        )
    denoised = grayscale.filter(ImageFilter.MedianFilter(size=3))
    autocontrasted = ImageOps.autocontrast(denoised)
    binarized = autocontrasted.point(lambda p: 255 if p > 150 else 0)
    return binarized


def ocr_with_preprocessing(images: list[Image.Image]) -> TierResult:
    """Tier 3: preprocess (deskew/denoise/binarize/upscale) + OCR retry."""
    texts = []
    confidences = []
    for image in images:
        image = _fix_orientation(image)
        preprocessed = _preprocess_for_ocr(image)
        text, confidence = _ocr_with_confidence(preprocessed)
        text = _merge_sparse_text(text, _ocr_sparse_text(preprocessed))
        texts.append(text)
        confidences.append(confidence)
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return TierResult(
        tier=3, text="\n\n".join(texts), confidence=overall_confidence, method="ocr_preprocessed"
    )
