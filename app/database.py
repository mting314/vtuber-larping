import os

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

DB_FILE = os.getenv("DATABASE_FILE", "vtuber_digest.db")
DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)


def init_db(target_engine=None):
    """Create tables / apply migrations. Defaults to the process-wide engine.

    `target_engine` lets callers initialise a second SQLite file (e.g. the
    merge scratch copy in app.persistence) through the same migration path.
    """
    eng = target_engine if target_engine is not None else engine
    SQLModel.metadata.create_all(eng)
    # Additive column migrations for SQLite files created by older versions.
    # Each is attempted independently; "duplicate column" just means it's applied.
    migrations = (
        "ALTER TABLE stream ADD COLUMN stream_category VARCHAR DEFAULT 'chatting'",
        "ALTER TABLE stream ADD COLUMN retry_count INTEGER DEFAULT 0",
        "ALTER TABLE stream ADD COLUMN last_attempted_at DATETIME",
    )
    with eng.connect() as conn:
        for ddl in migrations:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                conn.rollback()  # Column already exists


def get_session():
    with Session(engine) as session:
        yield session
