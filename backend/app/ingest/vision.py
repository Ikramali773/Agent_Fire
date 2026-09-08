"""Tier 4 of the OCR pipeline (§B.7.1): vision-LLM direct read, used when
Tiers 1-3 (text layer, OCR, preprocessed OCR retry) all came back
low-confidence - the scope doc specifically calls this out for
"handwriting or stamp-occlusion detected", since a vision model tends to
reason around partial occlusion better than a plain OCR engine can.

Unlike Tiers 1-3, this tier is NOT free per §B.7.1's cost table - it's the
one tier that costs real money per page, hence pipeline.py only ever
reaches it after Tiers 1-3 have already failed, and only if an LLM is
actually configured (LLMNotConfiguredError propagates up rather than being
swallowed here - the pipeline decides what "no LLM available" means for the
overall result, this module doesn't get to silently skip on its own).
"""

from __future__ import annotations

from app.llm.client import LLMClient

_PAGE_TEXT_SCHEMA_FIELD = "page_text"


def run_vision_tier(page_png_bytes: list[bytes], llm: LLMClient) -> str:
    """Reads each page image and asks the vision model to transcribe
    everything relevant to a fire-safety intake (not just literal OCR - the
    prompt asks it to describe what it can make out, similar to how a human
    reviewer would read a partially-occluded document). Pages are joined
    with a blank line, same convention as the OCR tiers in tiers.py, so
    downstream fact-extraction code doesn't need to know which tier
    produced the text it's reading.
    """
    texts = []
    for page_bytes in page_png_bytes:
        extracted = llm.extract_fields_from_image(
            image_bytes=page_bytes,
            media_type="image/png",
            field_types={_PAGE_TEXT_SCHEMA_FIELD: str},
            context=(
                "Transcribe every piece of text relevant to a fire-safety "
                "compliance intake that you can read on this page - project "
                "name, address/state/city, building height, floor counts, "
                "built-up area, occupancy type, existing fire safety "
                "systems mentioned, etc. Include it all as one block of "
                f"text in the '{_PAGE_TEXT_SCHEMA_FIELD}' field, in your own "
                "words summarizing what's legible - you don't need to "
                "reproduce the exact original layout."
            ),
        )
        page_text = extracted.get(_PAGE_TEXT_SCHEMA_FIELD, "")
        if page_text:
            texts.append(page_text)
    return "\n\n".join(texts)
