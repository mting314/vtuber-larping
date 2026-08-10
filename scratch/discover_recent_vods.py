import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import httpx
from app.ingestion import parse_youtube_atom_feed

vtubers = [
    ('Shiori Novella', 'UCgnfPPb9JI3e9A4cXHnWbyg'),
    ('Kobo Kanaeru', 'UCjLEmnpCNeisMxy134KPwWw'),
    ('Nerissa Ravencroft', 'UC_sFNM0z0MWm9A6WlKPuMMg'),
    ('Vestia Zeta', 'UCTvHWSfBZgtxE4sILOaurIQ'),
    ('Gawr Gura', 'UCoSrY_IQQVpmIRZ9Xf-y93g'),
    ('FUWAMOCO', 'UCt9H_RpQzhxzlyBxFqrdHqA'),
    ('Ironmouse', 'UCj_TYZ60NDQYY5QpUvOge9g'),
]

async def discover():
    print("=== Discovering Recent VODs for Tracked VTubers ===")
    discovered_vods = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, cid in vtubers:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    entries = parse_youtube_atom_feed(res.text)
                    print(f"[{name}] Found {len(entries)} candidate VODs in RSS feed.")
                    for e in entries:
                        print(f"   - [{e['published_at'][:10]}] '{e['title']}' (https://www.youtube.com/watch?v={e['video_id']})")
                        discovered_vods.append(e)
            except Exception as err:
                print(f"[{name}] Error fetching RSS: {err}")
                
    print(f"\nTotal Discovered Recent Candidate Streams: {len(discovered_vods)}")

if __name__ == "__main__":
    asyncio.run(discover())
