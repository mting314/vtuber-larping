import asyncio
import json
import sys
from datetime import datetime
from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import VTuber, Stream, JobStatus
from app.main import process_stream_pipeline
from app.logger import ingestion_logger

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    init_db()
    with open("scratch/batch_chatting_100.json", "r", encoding="utf-8") as f:
        streams_data = json.load(f)

    print(f"Loaded {len(streams_data)} candidate streams for batch ingestion.")
    ingestion_logger.info(f"Starting batch ingestion for {len(streams_data)} candidate streams.")

    queued_stream_ids = []

    with Session(engine) as session:
        for item in streams_data:
            v_name = item["vtuber"]
            agency = item["agency"]
            video_id = item["video_id"]
            title = item["title"]

            # Get or create VTuber
            vtuber = session.exec(select(VTuber).where(VTuber.name == v_name)).first()
            if not vtuber:
                vtuber = VTuber(name=v_name, channel_id=f"UC_{video_id}", agency=agency)
                session.add(vtuber)
                session.commit()
                session.refresh(vtuber)

            # Get or create Stream
            existing = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
            if not existing:
                stream = Stream(
                    video_id=video_id,
                    title=title,
                    thumbnail_url=item["thumbnail_url"],
                    status=JobStatus.PENDING,
                    published_at=datetime.utcnow(),
                    vtuber_id=vtuber.id
                )
                session.add(stream)
                session.commit()
                session.refresh(stream)
                queued_stream_ids.append(stream.id)
            elif existing.status in (JobStatus.PENDING, JobStatus.FAILED):
                existing.status = JobStatus.PENDING
                existing.error_message = None
                session.add(existing)
                session.commit()
                queued_stream_ids.append(existing.id)

    print(f"Successfully queued {len(queued_stream_ids)} streams into database!")

    # Process streams concurrently in batches of 5 to avoid API rate limits
    batch_size = 5
    for i in range(0, len(queued_stream_ids), batch_size):
        batch = queued_stream_ids[i:i + batch_size]
        print(f"\nProcessing batch {i//batch_size + 1}/{(len(queued_stream_ids)+batch_size-1)//batch_size} (Stream IDs: {batch})...")
        tasks = [process_stream_pipeline(sid) for sid in batch]
        await asyncio.gather(*tasks, return_exceptions=True)

    print("\n🎉 All 100 streams have been processed by the Map-Reduce pipeline!")

if __name__ == "__main__":
    asyncio.run(main())
