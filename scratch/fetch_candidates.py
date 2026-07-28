import asyncio
import json
import sys
from app.ingestion import poll_channel_rss

sys.stdout.reconfigure(encoding='utf-8')

vtubers = [
    ('Shiori Novella', 'Hololive English', 'UC1uv2Oq6kNxgATlCiez59zQ'),
    ('Kobo Kanaeru', 'Hololive ID', 'UCjLEmnpCNeisMxy114VwW4g'),
    ('Nerissa Ravencroft', 'Hololive English', 'UC_vMYWcD54522570CPwP03w'),
    ('Zeta Vestia', 'Hololive ID', 'UChN5BnyA1DAuXM29a6bUjEw'),
    ('Ironmouse', 'VShojo', 'UCvN5U9x6bU161N1-105-01g'),
    ('Gawr Gura', 'Hololive English', 'UCoSrY_IQQVpmIRZ9Xf-y93g'),
    ('Hakos Baelz', 'Hololive English', 'UCslvdqhVMidHCjsZhtmGyaQ'),
    ('FUWAMOCO', 'Hololive English', 'UCt9H_RpQzhxzlyBxFqrdHqA'),
    ('Usada Pekora', 'Hololive JP', 'UC1DCedRgGHBtnkFvGii50jQ'),
    ('Houshou Marine', 'Hololive JP', 'UCCzUftO8KOVkV4wQG1vkUvg')
]

async def fetch_candidates():
    candidates = []
    for name, agency, ch_id in vtubers:
        try:
            entries = await poll_channel_rss(ch_id)
            if entries:
                top = entries[0]
                candidates.append({
                    'vtuber': name,
                    'agency': agency,
                    'title': top['title'],
                    'video_id': top['video_id'],
                    'url': f"https://www.youtube.com/watch?v={top['video_id']}",
                    'published_at': top.get('published', 'Recent')
                })
            else:
                print(f"No RSS entries found for {name}")
        except Exception as e:
            print(f"Failed for {name}: {e}")
            
    with open("scratch/candidates.json", "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully fetched {len(candidates)} candidates!")

if __name__ == "__main__":
    asyncio.run(fetch_candidates())
