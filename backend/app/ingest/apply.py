"""Applies a document upload's extraction result onto a Case File - the
glue between app/ingest/pipeline.py (get text off the file) and
app/ingest/fact_extraction.py (get Case File fields out of that text), kept
separate from app/api/ so the route handler stays a thin HTTP adapter, same
pattern as app/dialogue/manager.py vs. app/api/case_files.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.ingest.fact_extraction import extract_case_file_facts
from app.ingest.pipeline import IngestResult, run_pipeline
from app.llm.client import LLMClient, LLMNotConfiguredError
from app.models.case_file import CaseFile, FieldSource, FieldSourceKind, SourceDocument


@dataclass
class IngestSummary:
    tier_used: int
    confidence: float
    needs_human_review: bool
    fields_extracted: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    fact_extraction_skipped_reason: str | None = None


def ingest_document(
    case_file: CaseFile, file_bytes: bytes, content_type: str, filename: str, llm: LLMClient
) -> tuple[CaseFile, IngestSummary]:
    result: IngestResult = run_pipeline(file_bytes, content_type, llm=llm)

    case_file.source_documents.append(
        SourceDocument(
            filename=filename,
            pages=result.page_count,
            extraction_tier_used=result.tier_used if 1 <= result.tier_used <= 5 else None,
            overall_confidence=result.confidence / 100.0,
        )
    )

    summary = IngestSummary(
        tier_used=result.tier_used,
        confidence=result.confidence,
        needs_human_review=result.needs_human_review,
        failure_reason=result.failure_reason,
    )

    if not result.text.strip():
        case_file.updated_at = datetime.now(timezone.utc)
        return case_file, summary

    try:
        extracted = extract_case_file_facts(result.text, llm)
    except LLMNotConfiguredError:
        summary.fact_extraction_skipped_reason = (
            "Text was extracted from the document, but no LLM is configured to parse it into "
            "structured fields - you'll need to answer the remaining questions in chat."
        )
        case_file.updated_at = datetime.now(timezone.utc)
        return case_file, summary

    if extracted:
        merged = {**case_file.model_dump(), **extracted}
        case_file = CaseFile.model_validate(merged)
        # Document-sourced facts are marked with lower confidence than a
        # user's direct chat answer (product scope §B.4/§B.7: "text
        # extracted from a plan is not geometry-verified and must not be
        # treated as higher-confidence just because it came from a 'plan'
        # rather than a letter") - scaled by this upload's own OCR/vision
        # confidence rather than a flat number, so a low-confidence Tier 3
        # scrape is visibly less trusted than a clean Tier 1 text layer.
        field_confidence = result.confidence / 100.0
        for field_name, value in extracted.items():
            case_file.field_sources[field_name] = FieldSource(
                value=value, source=FieldSourceKind.DOCUMENT, confidence=field_confidence
            )
        summary.fields_extracted = list(extracted.keys())

    case_file.updated_at = datetime.now(timezone.utc)
    return case_file, summary
