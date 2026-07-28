"""Persist the summary SQLite DB in GCS so it survives across CI runs.

The dashboard's data lives in an untracked SQLite file. Without this, every
deploy rebuilds the site from an empty DB and wipes all summaries. This module
pulls the DB from GCS before a build and pushes it back after ingestion.

Usage:
    python -m scratch.db_sync pull   # download DB from GCS (no-op if absent)
    python -m scratch.db_sync push   # upload local DB to GCS

Auth uses Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS in CI).
"""

import os
import sys

from google.cloud import storage

DB_FILE = os.getenv("DATABASE_FILE", "vtuber_digest.db")
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "vtuber-summaries")
BLOB_PATH = os.getenv("DB_BLOB_PATH", "state/vtuber_digest.db")


def _blob():
    client = storage.Client()
    return client.bucket(BUCKET_NAME).blob(BLOB_PATH)


def pull() -> None:
    blob = _blob()
    if not blob.exists():
        print(f"No DB at gs://{BUCKET_NAME}/{BLOB_PATH} yet — starting fresh.")
        return
    blob.download_to_filename(DB_FILE)
    print(f"Pulled DB from gs://{BUCKET_NAME}/{BLOB_PATH} -> {DB_FILE}")


def push() -> None:
    if not os.path.exists(DB_FILE):
        print(f"Local DB {DB_FILE} not found — nothing to push.")
        return
    blob = _blob()
    blob.upload_from_filename(DB_FILE)
    print(f"Pushed {DB_FILE} -> gs://{BUCKET_NAME}/{BLOB_PATH}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "pull":
        pull()
    elif cmd == "push":
        push()
    else:
        print("Usage: python -m scratch.db_sync [pull|push]")
        sys.exit(1)
