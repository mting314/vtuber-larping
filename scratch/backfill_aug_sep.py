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
from scratch.scan_missed_aug_sep_streams import scan_missed_streams

async def process_candidate(vtuber: VTuber, video_id: str, title: str):
    print(f"\n==================================================")
    print(f"Processing ({vtuber.name}): [{video_id}] '{title}'")
    print(f"==================================================")
    
    with Session(engine) as session:
        existing = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
        if existing and existing.status == JobStatus.COMPLETED:
            print(f"⏩ Stream {video_id} already completed in DB. Skipping.")
            return True

    # 1. Download subtitles
    subtitle_file, meta = download_youtube_subtitles(video_id)
    if not subtitle_file:
        print(f"⚠️ No captions/subtitles available yet for {video_id}. Skipping for now.")
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
                    error_message="Subtitles / Captions not yet available on YouTube",
                    vtuber_id=vtuber.id
                )
                session.add(stream)
                session.commit()
        return False

    cues = parse_vtt(subtitle_file)
    if not cues:
        print(f"⚠️ Subtitle file empty or unparseable for {video_id}. Skipping.")
        return False

    # 2. Chunk & summarize
    duration = meta.get('duration', 0)
    pub_date = meta.get('published_at') or datetime.utcnow()
    thumb = meta.get('thumbnail_url') or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    final_title = meta.get('title') or title
    
    chunks = chunk_cues(cues, interval_minutes=15)
    print(f"  Parsed {len(cues)} cues into {len(chunks)} 15-minute chunks. Starting Map-Reduce LLM summarization...")

    try:
        master_summary, standout_highlights, chunk_summaries, stream_category = await run_map_reduce_pipeline(
            vtuber_name=vtuber.name,
            stream_title=final_title,
            chunks=chunks
        )
    except Exception as e:
        print(f"❌ Gemini summarization error for {video_id}: {e}")
        return False

    # 3. Save to DB
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
            session.refresh(stream)
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
            session.refresh(stream)

        # Update summary
        existing_sum = session.exec(select(Summary).where(Summary.stream_id == stream.id)).first()
        if existing_sum:
            session.delete(existing_sum)
            session.commit()

        new_sum = Summary(
            stream_id=stream.id,
            master_summary=master_summary,
            standout_highlights_json=json.dumps(standout_highlights, ensure_ascii=False),
            chunk_data_json=json.dumps(chunk_summaries, ensure_ascii=False)
        )
        session.add(new_sum)
        session.commit()

    print(f"✅ Successfully ingested & saved Stream ID {stream.id}: '{final_title}'")
    return True

async def main():
    init_db()
    candidates = scan_missed_streams()
    print(f"\n==================================================")
    print(f"Starting batch backfill for {len(candidates)} missed streams...")
    print(f"==================================================\n")
    
    success_count = 0
    skipped_count = 0
    
    for vtuber, video_id, title in candidates:
        try:
            res = await process_candidate(vtuber, video_id, title)
            if res:
                success_count += 1
            else:
                skipped_count += 1
        except Exception as err:
            print(f"❌ Unexpected error processing {video_id}: {err}")
            skipped_count += 1

    print(f"\n==================================================")
    print(f"Backfill Complete!")
    print(f"Successfully Ingested: {success_count}")
    print(f"Skipped / Failed Captions: {skipped_count}")
    print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
