import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

import re
import yt_dlp
from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import Stream, VTuber

MEMBERS_ONLY_KEYWORDS = [
    "members only", "members-only", "member only", "members-only",
    "bookwyrm", "jailbirds+", "kobolonimbus", "members asmr", "member stream"
]

def is_members_only(entry: dict) -> bool:
    title = (entry.get('title') or '').lower()
    if any(k in title for k in MEMBERS_ONLY_KEYWORDS):
        return True
    
    # Check yt-dlp metadata fields
    availability = entry.get('availability') or ''
    if availability in ('subscriber_only', 'premium_only'):
        return True
        
    badges = entry.get('badges') or []
    if any('members' in str(b).lower() for b in badges):
        return True
        
    return False

def scan_missed_streams():
    init_db()
    print("=== Scanning All 7 Tracked VTuber Channels for Missed Streams (Aug 14 - Sep 14) ===\n")
    
    with Session(engine) as session:
        vtubers = session.exec(select(VTuber)).all()
        existing_vids = set(session.exec(select(Stream.video_id)).all())
        
        missed_candidates = []
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'playlistend': 15,
            'quiet': True,
            'no_warnings': True,
        }
        
        for v in vtubers:
            print(f"--- Channel: {v.name} ({v.agency}) ---")
            url = f"https://www.youtube.com/channel/{v.channel_id}/streams"
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info and 'entries' in info:
                        for entry in info['entries']:
                            vid = entry.get('id')
                            title = entry.get('title') or 'Untitled Stream'
                            if is_members_only(entry):
                                print(f"  [MEMBERS ONLY] ({vid}) '{title[:45]}'")
                                continue
                            
                            if vid and vid not in existing_vids:
                                print(f"  [MISSING]      ({vid}) '{title[:45]}'")
                                missed_candidates.append((v, vid, title))
                            elif vid:
                                print(f"  [IN DB]        ({vid}) '{title[:45]}'")
            except Exception as e:
                print(f"  ⚠️ Error scraping channel {v.name}: {e}")
            print()
            
        print(f"Found {len(missed_candidates)} missed stream VOD candidates (excluding members-only)!")
        return missed_candidates

if __name__ == "__main__":
    scan_missed_streams()
