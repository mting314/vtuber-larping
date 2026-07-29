import asyncio
import json
from datetime import datetime

from sqlmodel import Session, select

from app.database import engine, init_db
from app.models import JobStatus, Stream, Summary, VTuber
from app.storage import storage_manager
from app.summarizer import run_map_reduce_pipeline
from app.transcriber import chunk_cues, parse_vtt


async def seed_shiori_stream():
    init_db()
    video_id = "Nd9rzBUcOHA"
    
    with Session(engine) as session:
        # Get or create Shiori VTuber record
        shiori = session.exec(select(VTuber).where(VTuber.name == "Shiori Novella")).first()
        if not shiori:
            shiori = VTuber(name="Shiori Novella", channel_id="UC1uv2Oq6kNxgATlCiez59zQ", agency="Hololive English")
            session.add(shiori)
            session.commit()
            session.refresh(shiori)
            
        stream = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
        if not stream:
            stream = Stream(
                video_id=video_id,
                title="Peeking Respectfully While Slobbering in the Hot Springs Zatsudan",
                duration_seconds=8882,
                published_at=datetime.utcnow(),
                thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                status=JobStatus.FETCHING_TRANSCRIPT,
                vtuber_id=shiori.id
            )
            session.add(stream)
            session.commit()
            session.refresh(stream)
        stream_id = stream.id

    print(f"Reading transcript.en.vtt for video {video_id}...")
    vtt_text = ""
    try:
        with open("transcript.en.vtt", "r", encoding="utf-8") as f:
            vtt_text = f.read()
    except Exception as e:
        print(f"Could not read local transcript file: {e}")
        return
        
    gcs_uri = storage_manager.save_transcript(video_id, vtt_text)
    
    cues = parse_vtt(vtt_text)
    chunks = chunk_cues(cues, interval_minutes=15)
    print(f"Parsed {len(cues)} cues into {len(chunks)} 15-minute chunks.")
    
    with Session(engine) as session:
        stream = session.get(Stream, stream_id)
        stream.status = JobStatus.SUMMARIZING
        session.add(stream)
        session.commit()

    print("Running Map-Reduce LLM summarization pipeline...")
    master_summary, standout_highlights, chunk_summaries = await run_map_reduce_pipeline(
        vtuber_name="Shiori Novella",
        stream_title="Peeking Respectfully While Slobbering in the Hot Springs Zatsudan",
        chunks=chunks
    )
    
    with Session(engine) as session:
        stream = session.get(Stream, stream_id)
        stream.status = JobStatus.COMPLETED
        stream.gcs_transcript_uri = gcs_uri
        
        summary_obj = session.exec(select(Summary).where(Summary.stream_id == stream.id)).first()
        if not summary_obj:
            summary_obj = Summary(
                stream_id=stream.id,
                master_summary=master_summary,
                standout_highlights_json=json.dumps(standout_highlights),
                chunk_data_json=json.dumps(chunk_summaries)
            )
        else:
            summary_obj.master_summary = master_summary
            summary_obj.standout_highlights_json = json.dumps(standout_highlights)
            summary_obj.chunk_data_json = json.dumps(chunk_summaries)
            
        session.add(summary_obj)
        session.add(stream)
        session.commit()
        
    print(f"Successfully seeded summary for stream {video_id}!")

if __name__ == "__main__":
    asyncio.run(seed_shiori_stream())
