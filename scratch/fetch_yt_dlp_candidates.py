import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

vtubers = [
    ('Shiori Novella', 'Hololive English', 'https://www.youtube.com/@ShioriNovella/streams'),
    ('Kobo Kanaeru', 'Hololive ID', 'https://www.youtube.com/@KoboKanaeru/streams'),
    ('Nerissa Ravencroft', 'Hololive English', 'https://www.youtube.com/@NerissaRavencroft/streams'),
    ('Zeta Vestia', 'Hololive ID', 'https://www.youtube.com/@VestiaZeta/streams'),
    ('Ironmouse', 'VShojo', 'https://www.youtube.com/@IronmouseVODs/videos'),
    ('Gawr Gura', 'Hololive English', 'https://www.youtube.com/@GawrGura/streams'),
    ('Hakos Baelz', 'Hololive English', 'https://www.youtube.com/@HakosBaelz/streams'),
    ('FUWAMOCO', 'Hololive English', 'https://www.youtube.com/@FUWAMOCOch/streams'),
    ('Usada Pekora', 'Hololive JP', 'https://www.youtube.com/@UsadaPekora/streams'),
    ('Houshou Marine', 'Hololive JP', 'https://www.youtube.com/@HoushouMarine/streams')
]

def fetch_candidates():
    candidates = []
    for name, agency, channel_url in vtubers:
        print(f"Fetching latest stream for {name}...")
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-end", "1",
            "--dump-json",
            "--no-warnings",
            channel_url
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if res.stdout.strip():
                item = json.loads(res.stdout.strip().split('\n')[0])
                video_id = item.get("id")
                title = item.get("title", f"{name} Stream")
                candidates.append({
                    "vtuber": name,
                    "agency": agency,
                    "title": title,
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                })
        except Exception as e:
            print(f"Failed for {name}: {e}")

    with open("scratch/candidates.json", "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)

    print(f"Finished! Total candidates fetched: {len(candidates)}")

if __name__ == "__main__":
    fetch_candidates()
