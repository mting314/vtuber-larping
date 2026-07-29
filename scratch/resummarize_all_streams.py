import asyncio
import logging
import sys

from sqlmodel import Session, select

from app.database import engine
from app.models import JobStatus, Stream, Summary
from app.summarizer import run_map_reduce_pipeline
from app.transcriber import chunk_cues, download_youtube_subtitles, parse_vtt

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reprocess_stream(session: Session, stream: Stream):
    vtuber_name = stream.vtuber.name if stream.vtuber else "VTuber"
    logger.info(f"Re-summarizing Stream ID {stream.id}: {stream.title} ({vtuber_name})...")
    
    # 1. Download / fetch transcript
    subtitle_file, meta = download_youtube_subtitles(stream.video_id)
    if not subtitle_file:
        logger.warning(f"Could not fetch subtitles for video {stream.video_id}")
        return False
        
    with open(subtitle_file, "r", encoding="utf-8") as f:
        vtt_content = f.read()
        
    cues = parse_vtt(vtt_content)
    if not cues:
        logger.warning(f"No caption cues found for video {stream.video_id}")
        return False
        
    chunks = chunk_cues(cues, interval_minutes=15)
    
    # 2. Run Map-Reduce LLM summarization with new rules
    master_summary, standout_highlights, chunk_summaries = await run_map_reduce_pipeline(
        vtuber_name=vtuber_name,
        stream_title=stream.title,
        chunks=chunks
    )
    
    # 3. Update database
    existing_summary = session.exec(select(Summary).where(Summary.stream_id == stream.id)).first()
    if existing_summary:
        session.delete(existing_summary)
        session.commit()
        
    import json
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
    logger.info(f"✓ Re-summarized Stream ID {stream.id} successfully!")
    return True

async def main():
    print("=== Re-summarizing All Ingested Streams with Updated Standardization Rules ===")
    with Session(engine) as session:
        streams = session.exec(
            select(Stream).where(Stream.status == JobStatus.COMPLETED)
        ).all()
        
        print(f"Found {len(streams)} streams to re-summarize.")
        
        for idx, stream in enumerate(streams, 1):
            print(f"\n[{idx}/{len(streams)}] Processing Stream ID {stream.id}: {stream.title}")
            try:
                success = await reprocess_stream(session, stream)
                if success:
                    # Delay 2 seconds between Vertex AI requests to prevent quota throttling
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to re-summarize Stream ID {stream.id}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
