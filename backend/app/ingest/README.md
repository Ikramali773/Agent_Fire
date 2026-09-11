# Document ingest / OCR pipeline (§B.7)

Turns an uploaded PDF/PNG/JPEG (a plan, NOC letter, or certificate) into text, then into Case File
fields. Reachable via `POST /case-files/{id}/documents`; the glue for both steps is
`apply.ingest_document()`.

## The tiers (`pipeline.run_pipeline`)

Each tier only runs if the one before it wasn't good enough — cheapest/fastest first:

1. **Text layer** (`tiers.extract_text_layer`) — PyMuPDF pulls the PDF's native text layer
   directly, no image rendering or OCR at all. Free and exact when it works (a plan exported from
   CAD/Word), which is why it's tried first. Only applies to PDFs; skipped for PNG/JPEG.
   Additionally runs PyMuPDF's `page.find_tables()` on every page (`tiers._extract_tables_as_text`)
   and appends any ruled-line table it finds as clean `" | "`-delimited rows, tagged
   `[Table(s) detected on this page]`. This matters a lot for architectural drawings specifically:
   an "area statement" or door-schedule table sits inside its own ruled box on the sheet, and
   `get_text()` alone flattens the whole page in roughly reading order - scrambling a table's
   rows/columns together with whatever's drawn around it (dimension labels, notes, the drawing
   itself) into word soup an LLM can't reliably map back to fields. `find_tables()` instead uses the
   page's own ruling lines to recover the real row/column structure. Only works for a vector table
   in a native-text PDF; Tiers 2/3's OCR path has no equivalent yet (a known gap for scanned/
   rasterized drawings - see "What isn't built here yet").
2. **Standard OCR** (`tiers.ocr_standard`) — for scanned PDFs/images: rasterize each page
   (`tiers.render_pdf_pages`, 200 DPI), auto-correct orientation via Tesseract's OSD
   (`tiers._fix_orientation` — a real, observed Tesseract limitation: OSD needs multiple lines of
   text to detect rotation reliably, a single short line isn't enough signal), then run Tesseract
   and score the result by its own reported word-level confidence.
3. **Preprocessed OCR retry** (`tiers.ocr_with_preprocessing`) — if standard OCR's confidence is
   too low (`TIER2_MIN_CONFIDENCE`), retry after grayscale/upscale/denoise/binarize (Pillow only —
   no deskew, no OpenCV; a noisy phone photo of a printed certificate is the target case here, not
   a heavily skewed scan).
4. **Vision LLM** (`vision.run_vision_tier`) — if OCR still isn't confident enough
   (`pipeline.TIER4_CONFIDENCE`), send each page image to the configured backend's
   `generate_json_from_image` and ask it to transcribe the page. Only runs if an LLM backend is
   configured; skipped (not crashed) otherwise. **Always flagged `needs_human_review = True`**
   regardless of what confidence it reports back — a vision model's self-reported confidence isn't
   trustworthy enough yet to treat as equivalent to Tesseract's word-level score. This is a known
   simplification, not a hypothetical concern to fix later if it turns out to matter.
5. **Human review** — not a tier that runs code; it's the `needs_human_review` flag on the API
   response when nothing above produced a usable result, so the caller can prompt a person instead
   of silently trusting garbage text.

## Turning text into fields (`fact_extraction.extract_case_file_facts`)

Whatever text came out of the tiers above is run through the same `LLMClient.extract_fields`
machinery the chat flow uses, against `DOCUMENT_FIELD_TYPES` (the Case File's structured fields,
including `floor_wise_area` - a nested `list[FloorAreaItem]` the LLM fills straight from a detected
table's rows, distinct from `built_up_area_sqm`'s single whole-building total - and
`occupancy_subdivision`, so a drawing implying e.g. "a 5-star hotel" correctly skips the chat's
dedicated subdivision question too, not just the occupancy question).
`apply.ingest_document` then merges anything extracted into the Case File with
`FieldSourceKind.DOCUMENT`, at a confidence scaled by *that upload's* OCR/vision confidence
(`result.confidence / 100.0`) — not a flat number — per the product scope's warning that text
extracted from a plan is not geometry-verified and must not be treated as more trustworthy just
because it came from a "plan" rather than a letter. If no LLM is configured, the text is still
stored on the Case File's `source_documents`, and the response's `fact_extraction_skipped_reason`
explains why no fields came out of it — this never crashes or drops the document. The same summary
field distinguishes a temporarily rate-limited/unavailable provider (`LLMUnavailableError` - wait
and re-upload) from a genuinely unconfigured one (set an API key) - a live deployment hit the
former from Groq's free-tier per-minute output-token quota after a few uploads in quick succession,
and previously got an uncaught 500 instead of this message (see backend/README.md's LLM abstraction
section for the max_tokens + LLMUnavailableError fix).

## What isn't built here yet

- Real per-field confidence from the vision tier (see the "always human review" note above).
- Table reconstruction for the OCR path (Tiers 2/3) — `find_tables()` only works on a native-text
  PDF's vector ruling lines; a scanned/photographed drawing's schedule table still gets flattened
  into plain OCR text with no row/column structure recovered.
- Fields the OCR pipeline still doesn't extract even with table detection — kitchen presence/count
  and a door count/schedule were considered and deliberately deferred (per an explicit product
  decision) since today's digitized NBCS Table 7 lookups don't key off either one; only floor-wise
  area and occupancy_subdivision were added.
- The dialogue manager doesn't yet *offer* uploading as an intake step — see the backend README's
  "Not yet built" section.
- Multi-document conflict handling (two uploads disagreeing on the same field) beyond "last upload
  wins" — the dialogue manager's existing re-confirmation step is the only backstop today.
