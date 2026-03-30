from pathlib import Path

from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

from bgrules.config import DB_PATH

Base = declarative_base()


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    """Create the parent directory for a local sqlite database URL."""
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        return

    db_path = Path(db_url[len(prefix):])
    db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent_dir(DB_PATH)
engine = create_engine(DB_PATH)
Session = sessionmaker(bind=engine)


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)
    name = Column(String)
    url = Column(String)
    content = Column(Text)


Base.metadata.create_all(engine)
