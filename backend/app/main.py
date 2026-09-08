import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.case_files import router as case_files_router
from app.db.init_db import create_all_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent (CREATE TABLE IF NOT EXISTS semantics via SQLAlchemy's
    # create_all) - safe to run on every boot rather than requiring a
    # separate migration step for Phase 1. Revisit with real migrations
    # (Alembic) once the schema needs to change under existing data.
    create_all_tables()
    yield


app = FastAPI(
    title="Fire Safety & NOC Compliance Platform - API",
    description=(
        "Phase 1 backend (product scope Part B). Deterministic classification "
        "engine, report generator, LLM-driven dialogue manager, frontend, "
        "database persistence, and the OCR document-ingest pipeline are live; "
        "the RAG knowledge base is not yet wired in - see README.md."
    ),
    version="0.1.0-phase1",
    lifespan=lifespan,
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
