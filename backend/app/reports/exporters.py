"""Report exporters - Phase 2 (product roadmap: real Download PDF/DOCX from
the Reports page, previously just disabled buttons reserved for this).

Both formats are rendered from generate_report_markdown()'s exact markdown -
never a second source of truth for report content, and never a place that
invents or reformats facts. Markdown -> HTML (via the `markdown` package)
-> PDF (via PyMuPDF's Story/DocumentWriter, already a dependency for the
OCR pipeline - no new heavy/system dependency needed) or -> DOCX (a small
HTML walker over python-docx, since python-docx has no Markdown importer
of its own). The markdown these render is a fixed, simple subset -
headings, paragraphs, flat bullet lists, bold/italic, and (since the Phase 3
handoff pack) flat tables. Still no images and no nested lists: the
generators do not emit them, and a walker that pretends to support what it
has never been given is how silent wrong output happens.
"""

from __future__ import annotations

import io
import re
from html.parser import HTMLParser

import markdown as _markdown
import pymupdf
from docx import Document

from app.models.case_file import CaseFile
from app.reports.generator import generate_report_markdown

_PAGE_RECT = pymupdf.paper_rect("a4")
_CONTENT_RECT = _PAGE_RECT + (36, 36, -36, -36)

_PDF_CSS = """
* { font-family: sans-serif; }
h1 { font-size: 16pt; margin-bottom: 6pt; }
h2 { font-size: 13pt; margin-top: 14pt; margin-bottom: 4pt; }
body, p, li { font-size: 10.5pt; line-height: 1.4; }
"""


def render_pdf(markdown_text: str) -> bytes:
    """Renders ANY of this app's markdown documents to PDF.

    Takes the markdown rather than a CaseFile so the report and the Phase 3
    consultant handoff (app/reports/handoff.py) share one renderer instead
    of growing a second, subtly different one.
    """
    html_body = _markdown.markdown(markdown_text, extensions=["extra"])

    def contentfn(positions):
        return html_body

    def rectfn(rect_num, filled):
        return _PAGE_RECT, _CONTENT_RECT, None

    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    pymupdf.Story.write_stabilized(writer, contentfn, rectfn, user_css=_PDF_CSS)
    writer.close()
    return buffer.getvalue()


class _DocxHtmlWalker(HTMLParser):
    """Walks the flat h1/h2/p/ul>li/strong/em HTML that `markdown` produces
    from generate_report_markdown()'s output and builds the equivalent
    python-docx paragraphs/runs.
    """

    def __init__(self, document: Document):
        super().__init__(convert_charrefs=True)
        self._document = document
        self._paragraph = None
        self._bold = False
        self._italic = False
        self._code = False
        # Table state. Cells are buffered as plain text and the whole table
        # is emitted at </table>, because python-docx needs its dimensions
        # up front - it cannot grow a table row by row as HTML arrives.
        self._table_rows: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._header_row_index: int | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._table_rows = []
            self._header_row_index = None
            return
        if self._table_rows is not None:
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th"):
                self._cell = []
                if tag == "th" and self._header_row_index is None:
                    self._header_row_index = len(self._table_rows)
            return
        if tag in ("h1", "h2", "h3"):
            self._paragraph = self._document.add_heading(level=int(tag[1]))
        elif tag == "p":
            self._paragraph = self._document.add_paragraph()
        elif tag == "li":
            self._paragraph = self._document.add_paragraph(style="List Bullet")
        elif tag in ("strong", "b"):
            self._bold = True
        elif tag in ("em", "i"):
            self._italic = True
        elif tag == "code":
            self._code = True
        elif tag == "br" and self._paragraph is not None:
            self._paragraph.add_run().add_break()

    def handle_endtag(self, tag: str) -> None:
        if self._table_rows is not None:
            if tag in ("td", "th") and self._row is not None and self._cell is not None:
                self._row.append("".join(self._cell).strip())
                self._cell = None
            elif tag == "tr" and self._row is not None:
                self._table_rows.append(self._row)
                self._row = None
            elif tag == "table":
                self._emit_table()
            return
        if tag in ("strong", "b"):
            self._bold = False
        elif tag in ("em", "i"):
            self._italic = False
        elif tag == "code":
            self._code = False
        elif tag in ("p", "li", "h1", "h2", "h3"):
            self._paragraph = None

    def _emit_table(self) -> None:
        rows = [row for row in (self._table_rows or []) if row]
        header_index = self._header_row_index
        self._table_rows = None
        self._header_row_index = None
        if not rows:
            return
        columns = max(len(row) for row in rows)
        table = self._document.add_table(rows=len(rows), cols=columns)
        table.style = "Table Grid"
        for row_index, row in enumerate(rows):
            for column_index in range(columns):
                cell = table.cell(row_index, column_index)
                text = row[column_index] if column_index < len(row) else ""
                cell.text = text
                if row_index == header_index and cell.paragraphs[0].runs:
                    cell.paragraphs[0].runs[0].bold = True
        # Anything after the table starts a fresh paragraph rather than
        # appending into the last cell.
        self._paragraph = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
            return
        if self._table_rows is not None:
            # Whitespace between table tags - not content.
            return
        if self._paragraph is None:
            if not data.strip():
                return
            self._paragraph = self._document.add_paragraph()
        run = self._paragraph.add_run(data)
        run.bold = self._bold
        run.italic = self._italic
        if self._code:
            run.font.name = "Courier New"


def render_docx(markdown_text: str) -> bytes:
    """DOCX counterpart of render_pdf - same reason for taking markdown."""
    html_body = _markdown.markdown(markdown_text, extensions=["extra"])
    document = Document()
    _DocxHtmlWalker(document).feed(html_body)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9 _-]+")


def safe_report_filename(case_file: CaseFile) -> str:
    """A Content-Disposition-safe base filename (no extension) - strips
    anything that isn't a plain word character, space, hyphen or
    underscore so a project name can never inject a header, path segment,
    or quote into the download response.
    """
    name = _UNSAFE_FILENAME_CHARS.sub("", case_file.project_name or "").strip()
    return name or "fire-safety-report"
