import subprocess
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

vtubers = [
    ("Shiori Novella", "Hololive English", "https://www.youtube.com/@ShioriNovella/streams"),
    ("Kobo Kanaeru", "Hololive ID", "https://www.youtube.com/@KoboKanaeru/streams"),
    ("Nerissa Ravencroft", "Hololive English", "https://www.youtube.com/@NerissaRavencroft/streams"),
    ("Zeta Vestia", "Hololive ID", "https://www.youtube.com/@VestiaZeta/streams"),
    ("Ironmouse", "VShojo", "https://www.youtube.com/@IronmouseVODs/videos"),
    ("Gawr Gura", "Hololive English", "https://www.youtube.com/@GawrGura/streams"),
    ("Hakos Baelz", "Hololive English", "https://www.youtube.com/@HakosBaelz/streams"),
    ("FUWAMOCO", "Hololive English", "https://www.youtube.com/@FUWAMOCOch/streams"),
    ("Amelia Watson", "Hololive English", "https://www.youtube.com/@AmeliaWatson/streams"),
    ("Ninomae Ina'nis", "Hololive English", "https://www.youtube.com/@NinomaeInanis/streams")
]

def fetch_10_vods(vtuber_name, agency, channel_url):
    print(f"Fetching 10 recent VODs for {vtuber_name}...")
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", "20",
        "--dump-json",
        "--no-warnings",
        channel_url
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not res.stdout.strip():
        return []

    lines = res.stdout.strip().split('\n')
    vods = []
    for line in lines:
        if len(vods) >= 10:
            break
        try:
            item = json.loads(line)
            title = item.get("title", "")
            video_id = item.get("id", "")
            # Exclude shorts
            if video_id and not title.startswith("#") and "shorts" not in title.lower():
                vods.append({
                    "vtuber": vtuber_name,
                    "agency": agency,
                    "title": title,
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                })
        except Exception:
            continue
    return vods

def main():
    all_candidates = []
    summary_by_vtuber = {}
    
    for name, agency, url in vtubers:
        vods = fetch_10_vods(name, agency, url)
        all_candidates.extend(vods)
        summary_by_vtuber[name] = {
            "agency": agency,
            "count": len(vods),
            "sample_titles": [v["title"] for v in vods[:3]]
        }
        print(f"✓ [{name}] Found {len(vods)} VOD candidates.")

    with open("scratch/batch_100_candidates.json", "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)

    with open("scratch/summary_by_vtuber.json", "w", encoding="utf-8") as f:
        json.dump(summary_by_vtuber, f, indent=2, ensure_ascii=False)

    print(f"\nCompleted! Total streams fetched: {len(all_candidates)}")

if __name__ == "__main__":
    main()
