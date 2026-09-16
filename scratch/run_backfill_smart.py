import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import json
from datetime import datetime
from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import JobStatus, Stream, Summary, VTuber
from app.summarizer import run_map_reduce_pipeline
from app.transcriber import chunk_cues, download_youtube_subtitles, parse_vtt
from scratch.scan_missed_aug_sep_streams import is_members_only, scan_missed_streams

async def process_single(vtuber: VTuber, video_id: str, title: str):
    # Check members-only by title upfront
    if is_members_only({"title": title}):
        print(f"⏭️ [MEMBERS ONLY - SKIPPED] ({vtuber.name}) [{video_id}] '{title[:45]}'")
        return "MEMBERS_ONLY"

    with Session(engine) as session:
        existing = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
        if existing and existing.status == JobStatus.COMPLETED:
            print(f"⏩ [ALREADY DONE] ({vtuber.name}) [{video_id}] '{title[:40]}'")
            return "COMPLETED"

    # 1. Download subtitles
    subtitle_file, meta = download_youtube_subtitles(video_id)
    if not subtitle_file:
        print(f"⏭️ [NO SUBTITLES / MEMBERS ONLY] ({vtuber.name}) [{video_id}] '{title[:40]}'")
        with Session(engine) as session:
            stream = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
            if not stream:
                stream = Stream(
                    video_id=video_id,
                    title=meta.get('title') if meta else title,
                    duration_seconds=meta.get('duration', 0) if meta else 0,
                    published_at=meta.get('published_at') if (meta and meta.get('published_at')) else datetime.utcnow(),
                    thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                    status=JobStatus.FAILED,
                    error_message="Subtitles / Captions not yet available on YouTube (or members-only)",
                    vtuber_id=vtuber.id
                )
                session.add(stream)
                session.commit()
        return "NO_SUBTITLES"

    cues = parse_vtt(subtitle_file)
    if not cues:
        print(f"⏭️ [EMPTY CUES] ({vtuber.name}) [{video_id}] '{title[:40]}'")
        return "NO_CUES"

    # 2. Chunk & summarize
    duration = meta.get('duration', 0)
    pub_date = meta.get('published_at') or datetime.utcnow()
    thumb = meta.get('thumbnail_url') or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    final_title = meta.get('title') or title
    
    chunks = chunk_cues(cues, interval_minutes=15)
    print(f"⚡ [SUMMARIZING] ({vtuber.name}) [{video_id}] '{final_title[:40]}' ({len(chunks)} chunks)...")

    try:
        master_summary, standout_highlights, chunk_summaries, stream_category = await run_map_reduce_pipeline(
            vtuber_name=vtuber.name,
            stream_title=final_title,
            chunks=chunks
        )
    except Exception as e:
        print(f"❌ [SUMMARIZE ERROR] ({vtuber.name}) [{video_id}]: {e}")
        return "ERROR"

    # 3. Save to DB cleanly inside single session context
    with Session(engine) as session:
        stream = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
        if not stream:
            stream = Stream(
                video_id=video_id,
                title=final_title,
                duration_seconds=duration,
                published_at=pub_date,
                thumbnail_url=thumb,
                status=JobStatus.COMPLETED,
                stream_category=stream_category,
                vtuber_id=vtuber.id
            )
            session.add(stream)
            session.commit()
        else:
            stream.title = final_title
            stream.duration_seconds = duration
            stream.published_at = pub_date
            stream.thumbnail_url = thumb
            stream.stream_category = stream_category
            stream.status = JobStatus.COMPLETED
            stream.error_message = None
            session.add(stream)
            session.commit()

        # Refresh within session to get valid ID
        session.refresh(stream)
        stream_id = stream.id

        # Update summary
        existing_sum = session.exec(select(Summary).where(Summary.stream_id == stream_id)).first()
        if existing_sum:
            session.delete(existing_sum)
            session.commit()

        new_sum = Summary(
            stream_id=stream_id,
            master_summary=master_summary,
            standout_highlights_json=json.dumps(standout_highlights, ensure_ascii=False),
            chunk_data_json=json.dumps(chunk_summaries, ensure_ascii=False)
        )
        session.add(new_sum)
        session.commit()

    print(f"✅ [COMPLETED] Stream ID {stream_id}: ({vtuber.name}) [{video_id}] '{final_title[:45]}'")
    return "SUCCESS"

async def main():
    init_db()
    candidates = scan_missed_streams()
    print(f"\n==================================================")
    print(f"Processing {len(candidates)} candidates for backfill...")
    print(f"==================================================\n")
    
    stats = {"COMPLETED": 0, "MEMBERS_ONLY": 0, "NO_SUBTITLES": 0, "NO_CUES": 0, "ERROR": 0, "SUCCESS": 0}
    
    for vtuber, video_id, title in candidates:
        try:
            status = await process_single(vtuber, video_id, title)
            stats[status] = stats.get(status, 0) + 1
        except Exception as err:
            print(f"❌ [UNEXPECTED ERROR] [{video_id}]: {err}")
            stats["ERROR"] += 1

    print(f"\n==================================================")
    print(f"Backfill Run Finished!")
    print(f"Summary Stats: {stats}")
    print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
