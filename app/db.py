from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
engine = create_engine("sqlite:///data/db.sqlite")
Session = sessionmaker(bind=engine)

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)
    name = Column(String)
    url = Column(String)
    content = Column(Text)

Base.metadata.create_all(engine)