import asyncio
import sys
import random
from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import Stream, JobStatus
from app.main import process_stream_pipeline

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    init_db()
    with Session(engine) as session:
        failed_streams = session.exec(
            select(Stream).where(Stream.status == JobStatus.FAILED)
        ).all()
        failed_ids = [s.id for s in failed_streams]

    print(f"Found {len(failed_ids)} failed streams due to YouTube 429 subtitle rate limits.")
    print("Retrying failed streams sequentially with rate-limit delays (3-5 sec jitter per stream)...")

    success_count = 0
    for idx, sid in enumerate(failed_ids, 1):
        print(f"\n[{idx}/{len(failed_ids)}] Retrying Stream ID {sid}...")
        # Add random delay between requests to avoid YouTube 429 rate limiting
        await asyncio.sleep(random.uniform(3.0, 6.0))
        
        try:
            # Re-set status to pending
            with Session(engine) as session:
                st = session.get(Stream, sid)
                if st:
                    st.status = JobStatus.PENDING
                    st.error_message = None
                    session.add(st)
                    session.commit()

            await process_stream_pipeline(sid)
            
            with Session(engine) as session:
                st = session.get(Stream, sid)
                if st and st.status == JobStatus.COMPLETED:
                    success_count += 1
                    print(f"  ✓ Stream ID {sid} completed successfully!")
                else:
                    err = st.error_message if st else 'Unknown error'
                    print(f"  ✗ Stream ID {sid} failed: {err}")
        except Exception as e:
            print(f"  ✗ Error re-processing Stream ID {sid}: {e}")

    print(f"\n🎉 Retry Batch Completed! Recovered {success_count}/{len(failed_ids)} streams.")

if __name__ == "__main__":
    asyncio.run(main())
