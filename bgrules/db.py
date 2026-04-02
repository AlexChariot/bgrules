from pathlib import Path

from sqlalchemy import Column, Float, Integer, String, Text, create_engine
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


class GameInfo(Base):
    __tablename__ = "game_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_name = Column(String, unique=True, nullable=False, index=True)
    bgg_id = Column(Integer, nullable=False)
    bgg_name = Column(String, nullable=False)
    year_published = Column(Integer)
    average_rating = Column(Float)
    min_players = Column(Integer)
    max_players = Column(Integer)
    playing_time_minutes = Column(Integer)
    average_weight = Column(Float)
    fetched_at = Column(String, nullable=False)


def init_db() -> None:
    """Create all configured database tables."""
    Base.metadata.create_all(engine)


init_db()
