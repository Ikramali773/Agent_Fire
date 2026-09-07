"""In-memory Case File store.

Placeholder only. The product scope's tech stack (B.10) specifies PostgreSQL
for case files/session state/audit log - swapping this module for a real
Postgres-backed repository (same get/save/list interface) is a pure infra
task that shouldn't need to touch the engine, API routes, or report
generator. Do not build on top of this store's persistence being durable;
it is process-lifetime only and exists so the API is runnable/testable now.
"""

from __future__ import annotations

from app.models.case_file import CaseFile

_case_files: dict[str, CaseFile] = {}


def save(case_file: CaseFile) -> CaseFile:
    _case_files[case_file.session_id] = case_file
    return case_file


def get(session_id: str) -> CaseFile | None:
    return _case_files.get(session_id)


def delete_all() -> None:
    """Test-only helper to reset store state between test runs."""
    _case_files.clear()
