import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import json
import subprocess
import time
from datetime import datetime
from sqlmodel import Session, select

from app.database import engine
from app.ingestion import is_strict_chatting_stream
from app.models import JobStatus, Stream, Summary, VTuber
from app.summarizer import run_map_reduce_pipeline
from app.transcriber import chunk_cues, download_youtube_subtitles, parse_vtt

channels = [
    ('Shiori Novella', 'https://www.youtube.com/@ShioriNovella/streams', 'UCgnfPPb9JI3e9A4cXHnWbyg', 'Hololive English'),
    ('Kobo Kanaeru', 'https://www.youtube.com/@KoboKanaeru/streams', 'UCjLEmnpCNeisMxy134KPwWw', 'Hololive ID'),
    ('Nerissa Ravencroft', 'https://www.youtube.com/@NerissaRavencroft/streams', 'UC_sFNM0z0MWm9A6WlKPuMMg', 'Hololive English'),
    ('Vestia Zeta', 'https://www.youtube.com/@VestiaZeta/streams', 'UCTvHWSfBZgtxE4sILOaurIQ', 'Hololive ID'),
    ('Gawr Gura', 'https://www.youtube.com/@GawrGura/streams', 'UCoSrY_IQQVpmIRZ9Xf-y93g', 'Hololive English'),
    ('FUWAMOCO', 'https://www.youtube.com/@FUWAMOCOch/streams', 'UCt9H_RpQzhxzlyBxFqrdHqA', 'Hololive English'),
    ('Ironmouse', 'https://www.youtube.com/@Ironmouse/streams', 'UCj_TYZ60NDQYY5QpUvOge9g', 'VShojo'),
]

async def backfill():
    print("=== Starting Backfill for Missed VTuber Streams ===")
    
    with Session(engine) as session:
        existing_video_ids = set(session.exec(select(Stream.video_id)).all())
        print(f"Loaded {len(existing_video_ids)} existing stream video IDs from database.")

    candidate_videos = []
    
    for name, handle_url, cid, agency in channels:
        print(f"\nScanning recent VODs for {name} ({handle_url})...")
        cmd = ['yt-dlp', '--dump-json', '--playlist-end', '5', '--flat-playlist', handle_url]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.stdout:
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    vid = data.get('id')
                    title = data.get('title', '')
                    if vid and vid not in existing_video_ids:
                        candidate_videos.append({
                            'name': name,
                            'cid': cid,
                            'agency': agency,
                            'vid': vid,
                            'title': title,
                            'url': f"https://www.youtube.com/watch?v={vid}"
                        })
                        print(f"   ➕ Found missing chatting VOD: '{title}' ({vid})")
                except Exception as e:
                    pass

    print(f"\nFound {len(candidate_videos)} candidate VODs to backfill.")
    
    ingested_count = 0
    for item in candidate_videos:
        print(f"\nProcessing [{item['name']}] '{item['title']}' ({item['vid']})...")
        try:
            subtitle_file, meta = download_youtube_subtitles(item['vid'])
            if not subtitle_file:
                print(f"   ⚠️ Could not download subtitles for {item['vid']}, skipping.")
                continue
                
            cues = parse_vtt(subtitle_file)
            if not cues:
                print(f"   ⚠️ No subtitle cues found for {item['vid']}, skipping.")
                continue
                
            chunks = chunk_cues(cues, interval_minutes=15)
            master_summary, standout_highlights, chunk_summaries, stream_category = await run_map_reduce_pipeline(
                vtuber_name=item['name'],
                stream_title=item['title'],
                chunks=chunks
            )
            
            with Session(engine) as session:
                vtuber = session.exec(select(VTuber).where(VTuber.channel_id == item['cid'])).first()
                if not vtuber:
                    vtuber = session.exec(select(VTuber).where(VTuber.name == item['name'])).first()
                if not vtuber:
                    vtuber = VTuber(name=item['name'], channel_id=item['cid'], agency=item['agency'])
                    session.add(vtuber)
                    session.commit()
                    session.refresh(vtuber)
                    
                stream = Stream(
                    video_id=item['vid'],
                    title=item['title'],
                    duration_seconds=meta.get('duration', 0),
                    published_at=datetime.utcnow(),
                    thumbnail_url=meta.get('thumbnail_url', f"https://i.ytimg.com/vi/{item['vid']}/hqdefault.jpg"),
                    status=JobStatus.COMPLETED,
                    stream_category=stream_category,
                    vtuber_id=vtuber.id
                )
                session.add(stream)
                session.commit()
                session.refresh(stream)
                
                summary = Summary(
                    stream_id=stream.id,
                    master_summary=master_summary,
                    standout_highlights_json=json.dumps(standout_highlights, ensure_ascii=False),
                    chunk_data_json=json.dumps(chunk_summaries, ensure_ascii=False)
                )
                session.add(summary)
                session.commit()
                ingested_count += 1
                print(f"   ✓ Successfully ingested stream ID {stream.id}!")
                
        except Exception as err:
            print(f"   ❌ Error ingesting {item['vid']}: {err}")
            
    print(f"\n=== Backfill Finished! Successfully ingested {ingested_count} streams. ===")

if __name__ == "__main__":
    asyncio.run(backfill())
