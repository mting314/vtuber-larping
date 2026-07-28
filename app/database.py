import os

from sqlmodel import Session, SQLModel, create_engine

DB_FILE = os.getenv("DATABASE_FILE", "vtuber_digest.db")
DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
