import argparse
import asyncio
import json
import re
import sys
from datetime import datetime

from sqlmodel import Session, select

from app.database import engine
from app.models import JobStatus, Stream, Summary, VTuber
from app.summarizer import run_map_reduce_pipeline
from app.transcriber import chunk_cues, download_youtube_subtitles, parse_vtt

sys.stdout.reconfigure(encoding='utf-8')

async def ingest_url(url: str):
    print(f"=== Ingesting Stream URL: {url} ===")
    
    match = re.search(r'(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})', url)
    if not match:
        print("Error: Invalid YouTube URL format.")
        sys.exit(1)
        
    video_id = match.group(1)
    
    subtitle_file, meta = download_youtube_subtitles(video_id)
    if not subtitle_file:
        print(f"Error: Could not download subtitles for {video_id}.")
        sys.exit(1)
        
    title = meta.get('title', f"YouTube Stream ({video_id})")
    uploader = meta.get('channel', 'VTuber')
    duration = meta.get('duration', 0)
    thumbnail = meta.get('thumbnail_url', f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
    
    cues = parse_vtt(subtitle_file)
    if not cues:
        print("Error: No caption cues found.")
        sys.exit(1)
        
    chunks = chunk_cues(cues, interval_minutes=15)
    
    master_summary, standout_highlights, chunk_summaries, stream_category = await run_map_reduce_pipeline(
        vtuber_name=uploader,
        stream_title=title,
        chunks=chunks
    )
    
    with Session(engine) as session:
        # Check or create VTuber
        vtuber = session.exec(select(VTuber).where(VTuber.name == uploader)).first()
        if not vtuber:
            vtuber = VTuber(name=uploader, channel_id="", agency="Hololive English")
            session.add(vtuber)
            session.commit()
            session.refresh(vtuber)
            
        stream = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
        if not stream:
            stream = Stream(
                video_id=video_id,
                title=title,
                duration_seconds=duration,
                published_at=datetime.utcnow(),
                thumbnail_url=thumbnail,
                status=JobStatus.COMPLETED,
                stream_category=stream_category,
                vtuber_id=vtuber.id
            )
            session.add(stream)
            session.commit()
            session.refresh(stream)
        else:
            stream.stream_category = stream_category
            stream.status = JobStatus.COMPLETED
            session.add(stream)
            session.commit()
            
        summary = session.exec(select(Summary).where(Summary.stream_id == stream.id)).first()
        if summary:
            session.delete(summary)
            session.commit()
            
        new_summary = Summary(
            stream_id=stream.id,
            master_summary=master_summary,
            standout_highlights_json=json.dumps(standout_highlights, ensure_ascii=False),
            chunk_data_json=json.dumps(chunk_summaries, ensure_ascii=False)
        )
        session.add(new_summary)
        stream.status = JobStatus.COMPLETED
        session.add(stream)
        session.commit()
        print(f"✓ Successfully processed and saved Stream ID {stream.id}: '{title}'")

def main():
    parser = argparse.ArgumentParser(description="Ingest a single YouTube video URL into VTuber Digest")
    parser.add_argument("--url", required=True, help="YouTube video URL")
    args = parser.parse_args()
    
    asyncio.run(ingest_url(args.url))

if __name__ == "__main__":
    main()
