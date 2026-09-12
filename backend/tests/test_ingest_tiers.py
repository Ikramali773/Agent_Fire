"""Tests app/ingest/tiers.py against REAL PDFs and REAL Tesseract OCR calls -
no mocks. Fixture PDFs/images are generated on the fly with pymupdf/PIL
rather than checked in as binary files.
"""

import io

import pymupdf
from PIL import Image

from app.ingest.tiers import (
    TIER1_MIN_TEXT_LENGTH,
    _merge_sparse_text,
    _ocr_with_confidence,
    extract_text_layer,
    ocr_standard,
    ocr_with_preprocessing,
    render_pdf_pages,
)


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


def make_blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestTier1TextLayer:
    def test_extracts_native_text_with_high_confidence(self):
        pdf_bytes = make_text_pdf(
            ["Fire Safety Plan - Residential Apartment Building", "Height: 32 meters, State: Gujarat"]
        )
        result = extract_text_layer(pdf_bytes)
        assert result.tier == 1
        assert "Residential Apartment Building" in result.text
        assert result.confidence > 0

    def test_blank_pdf_gets_zero_confidence(self):
        result = extract_text_layer(make_blank_pdf())
        assert result.confidence == 0.0

    def test_short_text_below_threshold_gets_zero_confidence(self):
        pdf_bytes = make_text_pdf(["hi"])
        assert len("hi") < TIER1_MIN_TEXT_LENGTH
        result = extract_text_layer(pdf_bytes)
        assert result.confidence == 0.0


def make_table_pdf(rows: list[list[str]], col_widths: list[int] | None = None) -> bytes:
    """A ruled-line (vector) table, like an architectural drawing's area
    statement or door schedule box - real grid lines, not just aligned text,
    so pymupdf's find_tables() has real structure to detect.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    x0, y0 = 50, 50
    row_h = 20
    widths = col_widths or [100] * len(rows[0])
    total_width = sum(widths)
    n_rows = len(rows)

    for r in range(n_rows + 1):
        page.draw_line((x0, y0 + r * row_h), (x0 + total_width, y0 + r * row_h))
    x = x0
    for w in [0, *widths]:
        x += w if w != 0 else 0
        page.draw_line((x, y0), (x, y0 + n_rows * row_h))

    for r, row in enumerate(rows):
        x = x0
        for c, value in enumerate(row):
            page.insert_text((x + 5, y0 + r * row_h + 15), value, fontsize=9)
            x += widths[c]

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestTier1TableDetection:
    def test_ruled_line_table_is_extracted_as_structured_rows(self):
        pdf_bytes = make_table_pdf(
            [
                ["Floor", "Area (sqm)", "Remarks"],
                ["Ground", "120.5", "Retail"],
                ["First", "110.0", "Office"],
            ]
        )

        result = extract_text_layer(pdf_bytes)

        assert "Table(s) detected on this page" in result.text
        assert "Floor | Area (sqm) | Remarks" in result.text
        assert "Ground | 120.5 | Retail" in result.text
        assert "First | 110.0 | Office" in result.text

    def test_page_with_no_table_is_unaffected(self):
        pdf_bytes = make_text_pdf(["Just a plain paragraph of drawing notes, no table here."])
        result = extract_text_layer(pdf_bytes)
        assert "Table(s) detected" not in result.text


class TestMergeSparseText:
    def test_appends_sparse_text_that_adds_new_content(self):
        merged = _merge_sparse_text("Height 12 meters", "Floor Area Remarks Ground 120 Retail")
        assert "sparse-text OCR" in merged
        assert "Ground 120 Retail" in merged

    def test_does_not_append_when_sparse_text_adds_nothing_new(self):
        # Avoids noise/duplication when the primary pass already got
        # everything - only worth appending if it found something new.
        merged = _merge_sparse_text("Height 12 meters", "meters Height")
        assert merged == "Height 12 meters"

    def test_handles_empty_primary_text(self):
        merged = _merge_sparse_text("", "Floor Area Remarks")
        assert "Floor Area Remarks" in merged

    def test_handles_empty_sparse_text(self):
        assert _merge_sparse_text("Height 12 meters", "") == "Height 12 meters"


class TestTier2And3Ocr:
    def test_ocr_standard_reads_rendered_text_correctly(self):
        pdf_bytes = make_text_pdf(["Built-up area: 4500 sqm", "Floors above ground: 10"])
        images = render_pdf_pages(pdf_bytes)
        result = ocr_standard(images)
        assert result.tier == 2
        assert "4500" in result.text
        assert result.confidence > 60

    def test_ocr_standard_recovers_content_from_a_table_the_primary_pass_totally_misses(self):
        """Regression test for a real, confirmed Tesseract limitation:
        default full-page OCR (PSM 3, what image_to_data/image_to_string use
        with no config) can return NOTHING AT ALL for a ruled-line/bordered
        table image - not just a poor read, a total miss, because it
        misclassifies the bordered region as a non-text layout element. This
        specific table geometry (confirmed directly, not assumed) reproduces
        exactly that: image_to_data finds zero words at all. A rasterized
        architectural drawing's area-statement or door-schedule box can be
        this shape. The sparse-text supplementary pass (--psm 11) recovers
        at least partial content instead of losing the table entirely.
        """
        doc = pymupdf.open()
        page = doc.new_page()
        x0, y0, col_w, row_h = 50, 50, 120, 25
        rows_data = [
            ["Floor", "Area (sqm)", "Remarks"],
            ["Ground", "120.5", "Retail"],
            ["First", "110.0", "Office"],
        ]
        for r in range(len(rows_data) + 1):
            page.draw_line((x0, y0 + r * row_h), (x0 + 3 * col_w, y0 + r * row_h))
        for c in range(4):
            page.draw_line((x0 + c * col_w, y0), (x0 + c * col_w, y0 + len(rows_data) * row_h))
        for r, row in enumerate(rows_data):
            for c, value in enumerate(row):
                page.insert_text((x0 + c * col_w + 5, y0 + r * row_h + 17), value, fontsize=11)
        pdf_bytes = doc.tobytes()
        doc.close()

        images = render_pdf_pages(pdf_bytes)
        # Confirm the premise before testing the fix: the primary OCR pass
        # really does find nothing for this exact table.
        assert _ocr_with_confidence(images[0]) == ("", 0.0)

        result = ocr_standard(images)

        assert "sparse-text OCR" in result.text
        assert result.text.strip() != ""

    def test_ocr_corrects_180_degree_rotation(self):
        # Tesseract's orientation detection (OSD) needs a reasonable amount
        # of text to work reliably - a single short line isn't enough
        # signal, confirmed while writing this test, so this uses a
        # multi-line page like a real document would have.
        pdf_bytes = make_text_pdf(
            ["Occupancy: Storage building", "Height: 12 meters", "State: Maharashtra"]
        )
        images = render_pdf_pages(pdf_bytes)
        rotated = [images[0].rotate(180)]
        result = ocr_standard(rotated)
        assert "Storage" in result.text
        assert result.confidence > 60

    def test_preprocessing_tier_also_reads_correctly(self):
        pdf_bytes = make_text_pdf(["Number of staircases: 2", "Number of exits: 3"])
        images = render_pdf_pages(pdf_bytes)
        result = ocr_with_preprocessing(images)
        assert result.tier == 3
        assert "staircases" in result.text.lower()

    def test_blank_page_ocr_gets_low_confidence(self):
        images = render_pdf_pages(make_blank_pdf())
        result = ocr_standard(images)
        assert result.confidence == 0.0
        assert result.text.strip() == ""


class TestRenderPdfPages:
    def test_renders_one_image_per_page(self):
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        images = render_pdf_pages(pdf_bytes)
        assert len(images) == 2
        assert all(isinstance(img, Image.Image) for img in images)
