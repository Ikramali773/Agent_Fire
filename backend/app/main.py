import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.case_files import router as case_files_router
from app.api.invites import router as invites_router
from app.api.organisations import assignment_router, router as organisations_router
from app.api.users import router as users_router
from app.auth.tokens import using_default_secret
from app.mail import LoggingMailer, get_mailer
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


def _check_mail() -> None:
    """Says once, at boot, whether this deployment can actually send mail.

    Not an error: a deployment with no SMTP still works, and failing to
    start would break password reset, invites and assignment for anyone
    who has not configured a server. But a silent no-op is how people come
    to believe mail is working when it is not, so it is stated plainly.
    """
    if isinstance(get_mailer(), LoggingMailer):
        logging.getLogger("uvicorn.error").warning(
            "No SMTP configured (FIRE_AGENT_SMTP_HOST is unset), so NOTHING IS EMAILED. "
            "Password-reset links, reviewer invitations and assignment notices are written "
            "to this log instead. Password reset therefore only works for someone who can "
            "read it."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs Alembic migrations (see app/db/init_db.py), which is what keeps
    # a fresh checkout and the test suite zero-setup. Idempotent: on an
    # up-to-date database it is a version lookup and nothing else. Set
    # FIRE_AGENT_AUTO_MIGRATE=0 to make migrating a deploy step instead,
    # which is what a multi-worker deployment wants.
    create_all_tables()
    _check_auth_secret()
    _check_mail()
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
# Stripped, and empties dropped. Without this, the natural way to write
# the variable - "http://a.example.com, http://b.example.com", with a
# space after the comma - produced " http://b.example.com", which matches
# no browser Origin header and silently blocked that site. It fails closed,
# so the symptom is "the frontend mysteriously cannot reach the API"
# rather than a hole, but it is a poor thing to debug.
allowed_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

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
app.include_router(organisations_router)
app.include_router(assignment_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
