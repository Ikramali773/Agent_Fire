import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.case_files import router as case_files_router
from app.api.invites import router as invites_router
from app.api.users import router as users_router
from app.auth.tokens import using_default_secret
from app.db.init_db import create_all_tables


# Environments where running on the built-in signing key is a real
# exposure rather than a dev convenience. Anyone who knows that key - it is
# in this repository - can mint a session token for any account.
_PRODUCTION_ENVS = {"production", "prod", "staging"}


def _check_auth_secret() -> None:
    """Refuses to start a production deployment on the development signing
    key, and warns about it everywhere else.

    A warning alone is not enough for production: this is the difference
    between "every account is protected by a password" and "every account
    is open to anyone who has read the source".
    """
    if not using_default_secret():
        return
    environment = os.environ.get("FIRE_AGENT_ENV", "development").strip().lower()
    message = (
        "FIRE_AGENT_AUTH_SECRET is not set, so session tokens are signed with the "
        "development key that ships in this repository. Anyone who knows it can mint "
        "a token for any account. Set FIRE_AGENT_AUTH_SECRET to a long random value."
    )
    if environment in _PRODUCTION_ENVS:
        raise RuntimeError(f"Refusing to start with FIRE_AGENT_ENV={environment}: {message}")
    logging.getLogger("uvicorn.error").warning("SECURITY: %s", message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs Alembic migrations (see app/db/init_db.py), which is what keeps
    # a fresh checkout and the test suite zero-setup. Idempotent: on an
    # up-to-date database it is a version lookup and nothing else. Set
    # FIRE_AGENT_AUTO_MIGRATE=0 to make migrating a deploy step instead,
    # which is what a multi-worker deployment wants.
    create_all_tables()
    _check_auth_secret()
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
app.include_router(invites_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
