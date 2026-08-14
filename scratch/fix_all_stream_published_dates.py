import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

import yt_dlp
from datetime import datetime, timezone
from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import Stream

def fix_all_published_dates():
    init_db()
    print("=== Backfilling Real YouTube Broadcast Dates for All Streams in Database ===")
    
    with Session(engine) as session:
        streams = session.exec(select(Stream)).all()
        print(f"Total streams to inspect: {len(streams)}")
        
        ydl_opts = {'skip_download': True, 'quiet': True, 'no_warnings': True}
        
        updated_count = 0
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for s in streams:
                url = f"https://www.youtube.com/watch?v={s.video_id}"
                try:
                    info = ydl.extract_info(url, download=False)
                    if info:
                        ts = info.get('release_timestamp') or info.get('timestamp')
                        pub_dt = None
                        if ts:
                            pub_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                        elif info.get('upload_date'):
                            try:
                                pub_dt = datetime.strptime(info['upload_date'], '%Y%m%d')
                            except Exception:
                                pub_dt = None
                                
                        if pub_dt:
                            s.published_at = pub_dt
                            session.add(s)
                            updated_count += 1
                            print(f"  ✓ Stream ID {s.id:3} ({s.video_id}) -> {pub_dt.strftime('%Y-%m-%d')}")
                except Exception as e:
                    print(f"  ⚠️ Stream ID {s.id:3} ({s.video_id}) -> Skipped: {e}")
                    
        session.commit()
        print(f"\n🎉 Successfully updated {updated_count} stream published_at dates!")

if __name__ == "__main__":
    fix_all_published_dates()
