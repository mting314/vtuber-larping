"""Durable write-back of pipeline results to the GCS-hosted SQLite DB.

Why this exists
---------------
The Cloud Run container's SQLite file is ephemeral: it dies on scale-to-zero.
The gallery, meanwhile, is built from `gs://<bucket>/state/vtuber_digest.db`.
Without a write-back path, a WebSub-triggered summary is computed and then
thrown away — which is exactly what was happening.

Why it isn't just "upload the local file"
-----------------------------------------
A whole-file upload is a read-modify-write over shared state, and Cloud Run can
run many instances. Two instances that both start from generation N and both
upload would leave only the second one's work. So instead of pushing the local
DB, each writer merges *its own stream* into a fresh copy of the authoritative
remote DB, and commits with an `if_generation_match` precondition. If another
writer landed in between, the upload is rejected and we redo the merge against
the new remote state. The local DB is never treated as authoritative.

Row identity is keyed on natural keys (`Stream.video_id`, `VTuber.channel_id`),
never on autoincrement `id`, because ids are assigned per-database and will
disagree across instances.
"""

import logging
import os
import shutil
import tempfile
import threading

from sqlmodel import Session, create_engine, select

from app.database import get_session, init_db
from app.models import Stream, Summary, VTuber
from app.storage import storage_manager

logger = logging.getLogger(__name__)

# Serialises writers inside one process; the GCS generation precondition is what
# protects us across processes/instances.
_push_lock = threading.Lock()

_MAX_ATTEMPTS = 5

# Stream columns copied into the remote row. `id` and `vtuber_id` are excluded:
# both are database-local and get resolved on the remote side.
#
# Split by nullability. NOT NULL columns are only overwritten when the incoming
# value is present — otherwise a partially-populated snapshot would raise on
# flush and lose an otherwise-good summary. Nullable columns are always copied,
# so a successful retry can clear a stale error_message.
_STREAM_FIELDS_REQUIRED = (
    "title",
    "stream_category",
    "duration_seconds",
    "published_at",
    "status",
    # Must round-trip through GCS: the container is ephemeral, so if retry state
    # lived only locally the backoff would reset on every cold start and the
    # retry loop would be right back to hammering YouTube.
    "retry_count",
)
_STREAM_FIELDS_OPTIONAL = (
    "thumbnail_url",
    "gcs_transcript_uri",
    "error_message",
    "warning_message",
    "last_attempted_at",
)
_STREAM_FIELDS = _STREAM_FIELDS_REQUIRED + _STREAM_FIELDS_OPTIONAL


def snapshot_stream(stream_id: int) -> dict | None:
    """Read one stream (+ its summary and channel) out of the local DB.

    Returns a detached plain dict so the merge can run without holding a session
    open against the local database.
    """
    with next(get_session()) as session:
        stream = session.get(Stream, stream_id)
        if stream is None:
            return None

        payload = {field: getattr(stream, field) for field in _STREAM_FIELDS}
        payload["video_id"] = stream.video_id

        vtuber = stream.vtuber
        payload["vtuber"] = (
            {"channel_id": vtuber.channel_id, "name": vtuber.name, "agency": vtuber.agency}
            if vtuber
            else None
        )

        summary = stream.summary
        payload["summary"] = (
            {
                "master_summary": summary.master_summary,
                "standout_highlights_json": summary.standout_highlights_json,
                "chunk_data_json": summary.chunk_data_json,
            }
            if summary
            else None
        )
        return payload


def _apply_to(session: Session, payload: dict) -> None:
    """Upsert the snapshotted stream (+summary) into `session`'s database."""
    video_id = payload["video_id"]

    stream = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
    if stream is None:
        stream = Stream(video_id=video_id, title=payload["title"])
        session.add(stream)

    for field in _STREAM_FIELDS_REQUIRED:
        if payload.get(field) is not None:
            setattr(stream, field, payload[field])
    for field in _STREAM_FIELDS_OPTIONAL:
        setattr(stream, field, payload.get(field))

    # Resolve the channel in *this* database — vtuber ids differ per DB. Create
    # the row if the remote DB doesn't track this channel yet, so the stream is
    # never left orphaned.
    vt_payload = payload["vtuber"]
    if vt_payload:
        vtuber = session.exec(
            select(VTuber).where(VTuber.channel_id == vt_payload["channel_id"])
        ).first()
        if vtuber is None:
            vtuber = VTuber(**vt_payload)
            session.add(vtuber)
            session.commit()
            session.refresh(vtuber)
        stream.vtuber_id = vtuber.id

    session.commit()
    session.refresh(stream)

    sm_payload = payload["summary"]
    if sm_payload:
        summary = session.exec(select(Summary).where(Summary.stream_id == stream.id)).first()
        if summary is None:
            summary = Summary(stream_id=stream.id, **sm_payload)
            session.add(summary)
        else:
            for key, value in sm_payload.items():
                setattr(summary, key, value)
        session.commit()


def persist_stream_to_gcs(stream_id: int) -> bool:
    """Merge one stream's result into the authoritative GCS DB.

    Returns True once the merged DB is committed to GCS. Returns False if GCS is
    unavailable, the stream is missing, or we lost the compare-and-swap race
    _MAX_ATTEMPTS times in a row. Never raises — a persistence failure must not
    take down the pipeline that produced the summary.
    """
    payload = snapshot_stream(stream_id)
    if payload is None:
        logger.error(f"[Stream {stream_id}] Cannot persist: row not found in local DB.")
        return False

    if not storage_manager.bucket:
        logger.warning(f"[Stream {stream_id}] GCS unavailable — result stays local only.")
        return False

    with _push_lock:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            work_dir = tempfile.mkdtemp(prefix="vtuber-db-merge-")
            merge_path = os.path.join(work_dir, "vtuber_digest.db")
            try:
                generation = storage_manager.download_db_with_generation(merge_path)

                merge_engine = create_engine(
                    f"sqlite:///{merge_path}", connect_args={"check_same_thread": False}
                )
                try:
                    init_db(merge_engine)
                    with Session(merge_engine) as merge_session:
                        _apply_to(merge_session, payload)
                finally:
                    # Close every pooled connection so SQLite has fully flushed
                    # the file before we hand it to GCS.
                    merge_engine.dispose()

                if storage_manager.upload_db_if_unchanged(merge_path, generation):
                    logger.info(
                        f"[Stream {stream_id}] Persisted {payload['video_id']} to GCS "
                        f"(attempt {attempt})."
                    )
                    return True
                # Precondition failed: another instance wrote. Loop re-reads the
                # new remote state and re-applies our change on top of it.
            except Exception as e:
                logger.error(f"[Stream {stream_id}] GCS persistence attempt {attempt} failed: {e}", exc_info=True)
                return False
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

    logger.error(
        f"[Stream {stream_id}] Gave up persisting after {_MAX_ATTEMPTS} lost races — "
        "remote DB is under unexpectedly heavy write contention."
    )
    return False


def restore_db_from_gcs() -> bool:
    """Seed the container's local DB from GCS at startup.

    Best-effort: a cold container with no remote DB simply starts empty.
    """
    try:
        from app.database import DB_FILE

        if storage_manager.download_db(DB_FILE):
            logger.info("Restored summary DB from GCS.")
            return True
        logger.info("No DB in GCS (or GCS unavailable) — starting from an empty local DB.")
    except Exception as e:
        logger.error(f"Could not restore DB from GCS: {e}")
    return False
