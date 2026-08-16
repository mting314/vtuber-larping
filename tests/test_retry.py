"""Bounded-retry scheduling for failed ingestions.

The behaviour under test is what keeps the pipeline from re-earning a YouTube
bot block: a FAILED stream must be retried a few times on a widening backoff and
then left alone, rather than re-attempted on every cold start.
"""

from datetime import datetime, timedelta

from app.main import MAX_INGEST_RETRIES, RETRY_BASE_MINUTES, _retry_is_due
from app.models import JobStatus, Stream

NOW = datetime(2026, 8, 16, 12, 0, 0)


def _failed(retry_count=0, minutes_ago=None):
    return Stream(
        video_id="VID",
        title="t",
        status=JobStatus.FAILED,
        retry_count=retry_count,
        last_attempted_at=None if minutes_ago is None else NOW - timedelta(minutes=minutes_ago),
    )


def test_never_attempted_is_due_immediately():
    assert _retry_is_due(_failed(minutes_ago=None), NOW)


def test_backoff_widens_with_each_retry():
    # retry_count n waits RETRY_BASE_MINUTES * 2**n before the next attempt.
    for n in range(MAX_INGEST_RETRIES):
        wait = RETRY_BASE_MINUTES * (2**n)
        assert not _retry_is_due(_failed(n, minutes_ago=wait - 1), NOW), f"retry {n} fired early"
        assert _retry_is_due(_failed(n, minutes_ago=wait), NOW), f"retry {n} never fired"


def test_gives_up_at_the_cap():
    """The cap is what stops an unfixable stream from retrying forever."""
    assert not _retry_is_due(_failed(MAX_INGEST_RETRIES, minutes_ago=100_000), NOW)
    assert not _retry_is_due(_failed(MAX_INGEST_RETRIES + 1, minutes_ago=100_000), NOW)


def test_cold_start_does_not_reset_backoff():
    """Regression: retry state round-trips through GCS, so a restart must not re-fire.

    A stream attempted 5 minutes before the restart is still inside its backoff
    window and must stay quiet — the old behaviour re-queued everything on boot.
    """
    just_tried = _failed(retry_count=1, minutes_ago=5)
    assert not _retry_is_due(just_tried, NOW)


def test_retry_fields_round_trip_through_merge(tmp_path):
    from sqlmodel import Session, create_engine, select

    from app.database import init_db
    from app.persistence import _apply_to

    engine = create_engine(f"sqlite:///{tmp_path / 'remote.db'}")
    init_db(engine)
    attempted = NOW - timedelta(minutes=30)

    with Session(engine) as s:
        _apply_to(
            s,
            {
                "video_id": "VID",
                "title": "t",
                "stream_category": "chatting",
                "duration_seconds": 0,
                "published_at": NOW,
                "status": JobStatus.FAILED,
                "thumbnail_url": None,
                "gcs_transcript_uri": None,
                "error_message": "bot check",
                "warning_message": None,
                "retry_count": 3,
                "last_attempted_at": attempted,
                "vtuber": None,
                "summary": None,
            },
        )
        stream = s.exec(select(Stream)).first()
        assert stream.retry_count == 3
        assert stream.last_attempted_at == attempted


def test_sweep_claims_due_rows_and_skips_capped(tmp_path, monkeypatch):
    """Integration: the sweep re-queues only eligible rows and claims them first."""
    import asyncio

    from sqlmodel import Session, create_engine, select

    from app import main as app_main
    from app.database import init_db

    engine = create_engine(f"sqlite:///{tmp_path / 'local.db'}")
    init_db(engine)
    old = datetime.utcnow() - timedelta(hours=99)

    with Session(engine) as s:
        s.add(Stream(video_id="DUE", title="due", status=JobStatus.FAILED,
                     error_message="bot check", retry_count=0, last_attempted_at=old))
        s.add(Stream(video_id="CAPPED", title="capped", status=JobStatus.FAILED,
                     error_message="bot check", retry_count=MAX_INGEST_RETRIES,
                     last_attempted_at=old))
        s.add(Stream(video_id="DONE", title="done", status=JobStatus.COMPLETED))
        s.commit()

        persisted, launched = [], []
        monkeypatch.setattr(app_main, "_persist", lambda sid: _noop(persisted, sid))
        monkeypatch.setattr(app_main, "process_stream_pipeline", lambda sid: _noop(launched, sid))

        retried = asyncio.run(app_main.sweep_failed_retries(s))

        due = s.exec(select(Stream).where(Stream.video_id == "DUE")).first()
        capped = s.exec(select(Stream).where(Stream.video_id == "CAPPED")).first()

        assert len(retried) == 1 and retried[0] == due.id
        assert due.status == JobStatus.PENDING and due.retry_count == 1
        assert due.error_message is None
        assert capped.status == JobStatus.FAILED and capped.retry_count == MAX_INGEST_RETRIES
        # The claim must reach GCS before the work starts, or a second instance
        # sweeping concurrently would duplicate the map-reduce run.
        assert persisted == [due.id]
        assert launched == [due.id]


async def _noop(sink, stream_id):
    sink.append(stream_id)
