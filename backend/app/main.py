import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.case_files import router as case_files_router

app = FastAPI(
    title="Fire Safety & NOC Compliance Platform - API",
    description=(
        "Phase 1 backend (product scope Part B). Deterministic classification "
        "engine, report generator, LLM-driven dialogue manager, and frontend "
        "are live; the OCR ingest pipeline and RAG knowledge base are not yet "
        "wired in - see README.md."
    ),
    version="0.1.0-phase1",
)

# Dev-friendly default (Vite's dev server ports); override with a
# comma-separated list via FRONTEND_ORIGINS in any real deployment - this
# default is not meant to be production config.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
allowed_origins = os.environ.get("FRONTEND_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(case_files_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
