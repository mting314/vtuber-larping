"""Rebuild the SQLite DB from a static export directory (dist/-style layout).

Recovery / seed path when the DB is lost but the exported JSON still exists
(e.g. the gh-pages branch). Reads api/vtubers.json, api/streams.json and
api/streams/<id>.json and repopulates VTuber / Stream / Summary rows. No LLM
calls — this is a pure JSON -> SQLite reimport.

Usage:
    python -m scratch.seed_from_export <export_dir>   # default: dist
Then persist it:
    python -m scratch.db_sync push
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from app.database import engine, init_db
from app.models import JobStatus, Stream, Summary, VTuber


def _parse_dt(value):
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.utcnow()


def seed(export_dir: str = "dist") -> None:
    base = Path(export_dir)
    vtubers = json.loads((base / "api" / "vtubers.json").read_text(encoding="utf-8"))
    streams = json.loads((base / "api" / "streams.json").read_text(encoding="utf-8"))

    init_db()
    with Session(engine) as session:
        # VTubers (preserve ids so stream.vtuber_id references line up)
        for v in vtubers:
            if session.get(VTuber, v["id"]):
                continue
            session.add(VTuber(
                id=v["id"],
                name=v["name"],
                channel_id=v.get("channel_id") or f"unknown-{v['id']}",
                agency=v.get("agency", "Indies"),
            ))
        session.commit()

        imported = 0
        for s in streams:
            detail_path = base / "api" / "streams" / f"{s['id']}.json"
            detail = json.loads(detail_path.read_text(encoding="utf-8"))

            if session.exec(select(Stream).where(Stream.video_id == detail["video_id"])).first():
                continue

            stream = Stream(
                id=detail["id"],
                video_id=detail["video_id"],
                title=detail["title"],
                duration_seconds=detail.get("duration_seconds") or 0,
                published_at=_parse_dt(detail.get("published_at")),
                thumbnail_url=detail.get("thumbnail_url"),
                status=JobStatus(detail.get("status", "COMPLETED")),
                error_message=detail.get("error_message"),
                warning_message=detail.get("warning_message"),
                vtuber_id=(detail.get("vtuber") or {}).get("id"),
            )
            session.add(stream)
            session.commit()

            summary = detail.get("summary")
            if summary and summary.get("master_summary"):
                session.add(Summary(
                    stream_id=stream.id,
                    master_summary=summary["master_summary"],
                    standout_highlights_json=json.dumps(summary.get("standout_highlights") or []),
                    chunk_data_json=json.dumps(summary.get("chunks") or []),
                ))
                session.commit()
            imported += 1

    print(f"Seeded {len(vtubers)} VTubers and {imported} streams from {export_dir}/")


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else "dist")
