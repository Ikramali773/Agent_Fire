from fastapi import FastAPI

from app.api.case_files import router as case_files_router

app = FastAPI(
    title="Fire Safety & NOC Compliance Platform - API",
    description=(
        "Phase 1 backend (product scope Part B). Deterministic classification "
        "engine and report generator are live; the guided conversational "
        "intake, OCR ingest pipeline, and RAG knowledge base are not yet wired "
        "in - see README.md."
    ),
    version="0.1.0-phase1",
)

app.include_router(case_files_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
