import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

import yt_dlp
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import Stream

def fetch_date(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {'skip_download': True, 'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                ts = info.get('release_timestamp') or info.get('timestamp')
                if ts:
                    return video_id, datetime.fromtimestamp(ts, tz=timezone.utc)
                elif info.get('upload_date'):
                    return video_id, datetime.strptime(info['upload_date'], '%Y%m%d')
    except Exception as e:
        pass
    return video_id, None

def main():
    init_db()
    print("=== Fast Parallel Extraction of Real Stream Dates ===")
    with Session(engine) as session:
        streams = session.exec(select(Stream)).all()
        video_ids = [s.video_id for s in streams]
        
        results = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            for vid, dt in executor.map(fetch_date, video_ids):
                if dt:
                    results[vid] = dt
                    
        updated = 0
        for s in streams:
            if s.video_id in results:
                s.published_at = results[s.video_id]
                session.add(s)
                updated += 1
                print(f"  ✓ ID {s.id:3} ({s.video_id}) -> {results[s.video_id].strftime('%Y-%m-%d')}")
                
        session.commit()
        print(f"\n🎉 Successfully updated {updated} stream broadcast dates!")

if __name__ == "__main__":
    main()
