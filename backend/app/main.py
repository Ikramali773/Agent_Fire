import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.case_files import router as case_files_router
from app.api.users import router as users_router
from app.db.init_db import create_all_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent (CREATE TABLE IF NOT EXISTS semantics via SQLAlchemy's
    # create_all, plus a lightweight add-missing-columns pass - see
    # app/db/init_db.py) - safe to run on every boot rather than requiring
    # a separate migration step. Revisit with real migrations (Alembic)
    # once a schema change needs more than an additive nullable column
    # (a rename, a drop, a NOT NULL backfill).
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
    # Content-Disposition carries the export's filename (see
    # app/reports/exporters.py::safe_report_filename) - without exposing it,
    # the frontend and backend normally being on different ports/origins
    # means the browser hides this header from JS entirely (Fetch's default
    # CORS-safelisted response headers don't include it), and the report
    # download would silently fall back to a generic filename.
    expose_headers=["Content-Disposition"],
)

app.include_router(case_files_router)
app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
