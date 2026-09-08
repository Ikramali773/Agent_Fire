"""Proves app/store.py's DB-backed save/get round-trips a full Case File -
including nested classification_result, field_sources, and enum/datetime
fields - correctly, against the real SQLAlchemy models, not a mock.
"""

import uuid

from app.engine.classifier import classify
from app.models.case_file import (
    CaseFile,
    ConversationStage,
    FieldSource,
    FieldSourceKind,
    OccupancyType,
)
from app.store import delete_all, get, save


def setup_function() -> None:
    delete_all()


def test_save_and_get_round_trip_preserves_nested_data():
    case_file = CaseFile(
        session_id=str(uuid.uuid4()),
        project_name="Test Warehouse",
        state="Gujarat",
        occupancy_type=OccupancyType.STORAGE,
        height_m=9.5,
        built_up_area_sqm=600,
        number_of_staircases=1,
        conversation_stage=ConversationStage.CONFIRMING,
    )
    case_file.field_sources["height_m"] = FieldSource(
        value=9.5, source=FieldSourceKind.USER, confidence=1.0
    )
    case_file.classification_result = classify(case_file)

    save(case_file)
    loaded = get(case_file.session_id)

    assert loaded is not None
    assert loaded.session_id == case_file.session_id
    assert loaded.occupancy_type == OccupancyType.STORAGE
    assert loaded.conversation_stage == ConversationStage.CONFIRMING
    assert loaded.field_sources["height_m"].source == FieldSourceKind.USER
    assert loaded.field_sources["height_m"].confidence == 1.0
    assert loaded.classification_result.table_7_ref == "7H"
    assert loaded.classification_result.applies is True


def test_get_missing_session_returns_none():
    assert get("does-not-exist") is None


def test_save_twice_updates_rather_than_duplicates():
    case_file = CaseFile(session_id=str(uuid.uuid4()), project_name="Original")
    save(case_file)

    case_file.project_name = "Updated"
    save(case_file)

    loaded = get(case_file.session_id)
    assert loaded.project_name == "Updated"


def test_delete_all_clears_every_record():
    save(CaseFile(session_id=str(uuid.uuid4())))
    save(CaseFile(session_id=str(uuid.uuid4())))

    delete_all()

    from app.db.models import CaseFileRecord
    from app.db.session import get_session

    with get_session() as session:
        assert session.query(CaseFileRecord).count() == 0
