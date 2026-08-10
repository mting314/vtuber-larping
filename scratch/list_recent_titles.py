import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

import json
import subprocess
from sqlmodel import Session, select
from app.database import engine
from app.models import Stream

channels = [
    ('Shiori Novella', 'https://www.youtube.com/@ShioriNovella/streams'),
    ('Kobo Kanaeru', 'https://www.youtube.com/@KoboKanaeru/streams'),
    ('Nerissa Ravencroft', 'https://www.youtube.com/@NerissaRavencroft/streams'),
    ('Vestia Zeta', 'https://www.youtube.com/@VestiaZeta/streams'),
    ('Gawr Gura', 'https://www.youtube.com/@GawrGura/streams'),
    ('FUWAMOCO', 'https://www.youtube.com/@FUWAMOCOch/streams'),
    ('Ironmouse', 'https://www.youtube.com/@Ironmouse/streams'),
]

with Session(engine) as session:
    existing_ids = set(session.exec(select(Stream.video_id)).all())

print("=== Scanning All Recent Stream VOD Titles (/streams) ===")
for name, handle_url in channels:
    print(f"\n--- {name} ---")
    cmd = ['yt-dlp', '--dump-json', '--playlist-end', '5', '--flat-playlist', handle_url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stdout:
        for line in res.stdout.splitlines():
            if not line.strip(): continue
            try:
                data = json.loads(line)
                vid = data.get('id')
                title = data.get('title', '')
                in_db = "✅ IN DB" if vid in existing_ids else "❌ NOT IN DB"
                print(f"[{in_db}] ({vid}) '{title}'")
            except Exception as e:
                pass
