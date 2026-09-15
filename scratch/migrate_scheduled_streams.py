import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import JobStatus, Stream

def migrate_scheduled_streams():
    init_db()
    print("=== Migrating Upcoming Stream Placeholders & Premieres to SCHEDULED Status ===")
    
    with Session(engine) as session:
        failed_streams = session.exec(select(Stream).where(Stream.status == JobStatus.FAILED)).all()
        
        migrated_count = 0
        for s in failed_streams:
            err = (s.error_message or '').lower()
            if 'scheduled' in err or 'upcoming' in err or 'begin in' in err or 'pending youtube' in err or 'teaser' in err:
                s.status = JobStatus.SCHEDULED
                s.error_message = "Upcoming Stream / Premiere — awaiting stream completion & caption generation"
                session.add(s)
                migrated_count += 1
                title = (s.title or '')[:40]
                print(f"  ⏳ Migrated ID {s.id:3} ({s.video_id}) -> SCHEDULED: '{title}'")
                
        session.commit()
        print(f"\n🎉 Successfully migrated {migrated_count} streams to SCHEDULED status!")

if __name__ == "__main__":
    migrate_scheduled_streams()
