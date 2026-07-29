import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

vtuber_channels = [
    ("Shiori Novella", "Hololive English", "https://www.youtube.com/@ShioriNovella/streams"),
    ("Kobo Kanaeru", "Hololive ID", "https://www.youtube.com/@KoboKanaeru/streams"),
    ("Nerissa Ravencroft", "Hololive English", "https://www.youtube.com/@NerissaRavencroft/streams"),
    ("Zeta Vestia", "Hololive ID", "https://www.youtube.com/@VestiaZeta/streams"),
    ("Ironmouse", "VShojo", "https://www.youtube.com/@IronmouseVODs/videos"),
    ("Gawr Gura", "Hololive English", "https://www.youtube.com/@GawrGura/streams"),
    ("Hakos Baelz", "Hololive English", "https://www.youtube.com/@HakosBaelz/streams"),
    ("FUWAMOCO", "Hololive English", "https://www.youtube.com/@FUWAMOCOch/streams"),
    ("Usada Pekora", "Hololive JP", "https://www.youtube.com/@UsadaPekora/streams"),
    ("Houshou Marine", "Hololive JP", "https://www.youtube.com/@HoushouMarine/streams")
]

def get_latest_vod(channel_url):
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", "5",
        "--dump-json",
        "--no-warnings",
        channel_url
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not res.stdout.strip():
        return None
        
    lines = res.stdout.strip().split('\n')
    for line in lines:
        try:
            item = json.loads(line)
            title = item.get("title", "")
            video_id = item.get("id", "")
            # Filter out shorts, upcoming streams, or premieres
            if video_id and not title.startswith("#") and "shorts" not in title.lower():
                return {
                    "video_id": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                }
        except Exception:
            continue
    return None

def main():
    results = []
    print("Extracting 10 candidate streams from 10 VTubers...")
    for name, agency, url in vtuber_channels:
        vod = get_latest_vod(url)
        if vod:
            results.append({
                "vtuber": name,
                "agency": agency,
                "title": vod["title"],
                "video_id": vod["video_id"],
                "url": vod["url"],
                "thumbnail_url": vod["thumbnail_url"]
            })
            print(f"✓ Found candidate for {name}: {vod['title']} ({vod['video_id']})")
        else:
            print(f"✗ Could not find candidate for {name}")

    with open("scratch/candidates_clean.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
