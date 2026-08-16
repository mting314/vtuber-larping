"""Merge semantics for the GCS write-back path (app.persistence._apply_to).

These cover the failure modes that would silently corrupt the shared DB: id
collisions between independently-numbered databases, duplicate rows on retry,
and summaries getting attached to the wrong stream.
"""

from datetime import datetime

from sqlmodel import Session, create_engine, select

from app.database import init_db
from app.models import JobStatus, Stream, Summary, VTuber
from app.persistence import _apply_to

CHANNEL = "UCgnfPPb9JI3e9A4cXHnWbyg"
BROADCAST = datetime(2026, 8, 14, 20, 35, 0)


def _db(tmp_path, name):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    init_db(engine)
    return engine


def _payload(video_id="VID_NEW", title="New Stream", master="master text"):
    return {
        "video_id": video_id,
        "title": title,
        "stream_category": "chatting",
        "duration_seconds": 3600,
        "published_at": BROADCAST,
        "thumbnail_url": None,
        "status": JobStatus.COMPLETED,
        "gcs_transcript_uri": None,
        "error_message": None,
        "warning_message": None,
        "retry_count": 0,
        "last_attempted_at": None,
        "vtuber": {"channel_id": CHANNEL, "name": "Shiori Novella", "agency": "Hololive English"},
        "summary": {
            "master_summary": master,
            "standout_highlights_json": "[]",
            "chunk_data_json": "[]",
        },
    }


def test_merge_does_not_collide_with_existing_ids(tmp_path):
    """A stream that was id=1 in its own DB must not overwrite remote id=1."""
    engine = _db(tmp_path, "remote.db")
    with Session(engine) as s:
        s.add(VTuber(name="IRyS", channel_id="UC8rcEBzJSleTkf_-agPM20g", agency="Hololive English"))
        s.commit()
        s.add(Stream(video_id="VID_REMOTE", title="Pre-existing", status=JobStatus.COMPLETED))
        s.commit()

        _apply_to(s, _payload())

        rows = s.exec(select(Stream)).all()
        assert {r.video_id for r in rows} == {"VID_REMOTE", "VID_NEW"}
        assert s.exec(select(Stream).where(Stream.video_id == "VID_REMOTE")).first().title == "Pre-existing"


def test_merge_is_idempotent(tmp_path):
    """Re-applying after a lost compare-and-swap must not duplicate rows."""
    engine = _db(tmp_path, "remote.db")
    with Session(engine) as s:
        _apply_to(s, _payload())
        _apply_to(s, _payload(master="revised text"))

        assert len(s.exec(select(Stream)).all()) == 1
        assert len(s.exec(select(Summary)).all()) == 1
        assert len(s.exec(select(VTuber)).all()) == 1
        assert s.exec(select(Summary)).first().master_summary == "revised text"


def test_merge_binds_summary_to_remapped_stream_id(tmp_path):
    engine = _db(tmp_path, "remote.db")
    with Session(engine) as s:
        s.add(Stream(video_id="VID_REMOTE", title="Pre-existing", status=JobStatus.COMPLETED))
        s.commit()

        _apply_to(s, _payload())

        stream = s.exec(select(Stream).where(Stream.video_id == "VID_NEW")).first()
        summary = s.exec(select(Summary)).first()
        assert stream.id != 1, "expected a fresh id, not the one it held locally"
        assert summary.stream_id == stream.id


def test_merge_survives_missing_published_at(tmp_path):
    """A snapshot with no broadcast date must still land, not abort the merge.

    published_at is NOT NULL, so blindly copying None would raise on flush and
    throw away a summary that cost a full map-reduce run to produce.
    """
    engine = _db(tmp_path, "remote.db")
    payload = _payload()
    payload["published_at"] = None

    with Session(engine) as s:
        _apply_to(s, payload)

        stream = s.exec(select(Stream).where(Stream.video_id == "VID_NEW")).first()
        assert stream is not None
        assert stream.published_at is not None
        assert s.exec(select(Summary)).first().master_summary == "master text"


def test_merge_preserves_broadcast_date(tmp_path):
    engine = _db(tmp_path, "remote.db")
    with Session(engine) as s:
        _apply_to(s, _payload())
        assert s.exec(select(Stream)).first().published_at == BROADCAST


def test_merge_clears_stale_error_on_success(tmp_path):
    """A retry that succeeds must not leave the old failure message behind."""
    engine = _db(tmp_path, "remote.db")
    with Session(engine) as s:
        failed = _payload()
        failed["status"] = JobStatus.FAILED
        failed["error_message"] = "No auto-captions or subtitles available yet."
        failed["summary"] = None
        _apply_to(s, failed)

        _apply_to(s, _payload())

        stream = s.exec(select(Stream)).first()
        assert stream.status == JobStatus.COMPLETED
        assert stream.error_message is None


def test_merge_resolves_vtuber_by_channel_not_id(tmp_path):
    """Channel already present remotely under a different id -> reuse, don't duplicate."""
    engine = _db(tmp_path, "remote.db")
    with Session(engine) as s:
        s.add(VTuber(name="IRyS", channel_id="UC8rcEBzJSleTkf_-agPM20g", agency="Hololive English"))
        s.commit()
        s.add(VTuber(name="Shiori Novella", channel_id=CHANNEL, agency="Hololive English"))
        s.commit()
        shiori_id = s.exec(select(VTuber).where(VTuber.channel_id == CHANNEL)).first().id

        _apply_to(s, _payload())

        assert len(s.exec(select(VTuber)).all()) == 2, "should not have created a duplicate channel"
        assert s.exec(select(Stream).where(Stream.video_id == "VID_NEW")).first().vtuber_id == shiori_id
