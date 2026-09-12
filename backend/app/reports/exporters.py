"""Report exporters - Phase 2 (product roadmap: real Download PDF/DOCX from
the Reports page, previously just disabled buttons reserved for this).

Both formats are rendered from generate_report_markdown()'s exact markdown -
never a second source of truth for report content, and never a place that
invents or reformats facts. Markdown -> HTML (via the `markdown` package)
-> PDF (via PyMuPDF's Story/DocumentWriter, already a dependency for the
OCR pipeline - no new heavy/system dependency needed) or -> DOCX (a small
HTML walker over python-docx, since python-docx has no Markdown importer
of its own). The report's markdown is a fixed, simple subset (headings,
paragraphs, a flat bullet list, bold/italic) - see generator.py - so this
walker deliberately doesn't need to handle tables, images, or nested lists.
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


def render_pdf(case_file: CaseFile) -> bytes:
    html_body = _markdown.markdown(generate_report_markdown(case_file), extensions=["extra"])

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

    def handle_starttag(self, tag: str, attrs) -> None:
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
        if tag in ("strong", "b"):
            self._bold = False
        elif tag in ("em", "i"):
            self._italic = False
        elif tag == "code":
            self._code = False
        elif tag in ("p", "li", "h1", "h2", "h3"):
            self._paragraph = None

    def handle_data(self, data: str) -> None:
        if self._paragraph is None:
            if not data.strip():
                return
            self._paragraph = self._document.add_paragraph()
        run = self._paragraph.add_run(data)
        run.bold = self._bold
        run.italic = self._italic
        if self._code:
            run.font.name = "Courier New"


def render_docx(case_file: CaseFile) -> bytes:
    html_body = _markdown.markdown(generate_report_markdown(case_file), extensions=["extra"])
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
