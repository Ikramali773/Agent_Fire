from app.db.models import Base
from app.db.session import get_engine


def create_all_tables() -> None:
    Base.metadata.create_all(bind=get_engine())
