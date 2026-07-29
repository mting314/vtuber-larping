"""Persist the summary SQLite DB in GCS so it survives across CI runs.

The dashboard's data lives in an untracked SQLite file. Without this, every
deploy rebuilds the site from an empty DB and wipes all summaries. This module
pulls the DB from GCS before a build and pushes it back after ingestion.

The actual GCS logic lives in app.storage.StorageManager (so the Cloud Run
runtime image and CI share one implementation); this is just a CLI wrapper.

Usage:
    python -m scratch.db_sync pull   # download DB from GCS (no-op if absent)
    python -m scratch.db_sync push   # upload local DB to GCS

Auth uses Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS in CI).
"""

import sys

from app.database import DB_FILE
from app.storage import storage_manager


def pull() -> None:
    if storage_manager.download_db(DB_FILE):
        print(f"Pulled DB -> {DB_FILE}")
    else:
        print("No DB in GCS yet (or GCS unavailable) — starting fresh.")


def push() -> None:
    if storage_manager.upload_db(DB_FILE):
        print(f"Pushed {DB_FILE} to GCS.")
    else:
        print(f"Nothing pushed ({DB_FILE} missing or GCS unavailable).")


def push_cookies(file_path: str = "youtube_cookies.txt") -> None:
    if storage_manager.upload_cookies(file_path):
        print(f"Pushed cookies ({file_path}) -> GCS gs://{storage_manager.bucket.name}/state/youtube_cookies.txt")
    else:
        print(f"Failed to push cookies ({file_path} missing or GCS unavailable).")


def pull_cookies(file_path: str = "youtube_cookies.txt") -> None:
    if storage_manager.download_cookies(file_path):
        print(f"Pulled cookies from GCS -> {file_path}")
    else:
        print("No cookies in GCS (or GCS unavailable).")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    target_file = sys.argv[2] if len(sys.argv) > 2 else "youtube_cookies.txt"
    if cmd == "pull":
        pull()
    elif cmd == "push":
        push()
    elif cmd in ("push-cookies", "push_cookies"):
        push_cookies(target_file)
    elif cmd in ("pull-cookies", "pull_cookies"):
        pull_cookies(target_file)
    else:
        print("Usage: python -m scratch.db_sync [pull|push|push-cookies|pull-cookies] [cookies_file_path]")
        sys.exit(1)
