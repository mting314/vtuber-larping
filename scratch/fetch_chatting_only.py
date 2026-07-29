import json
import subprocess
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
    ("Ninomae Ina'nis", "Hololive English", "https://www.youtube.com/@NinomaeInanis/streams"),
    ("IRyS", "Hololive English", "https://www.youtube.com/@IRyS/streams")
]

EXCLUDE_WORDS = [
    "watchalong", "movie", "karaoke", "live", "concert", "3d live", "mini live",
    "playthrough", "gameplay", "shorts", "gacha", "game", "cover", "original song",
    "minecraft", "valorant", "apex", "elden ring", "dark souls", "resident evil",
    "mario kart", "palworld", "overcooked", "phasmophobia", "lethal company", "vrchat",
    "pratfall", "poppucom"
]

CHAT_WORDS = [
    "chat", "chatting", "zatsudan", "雑談", "rambles", "talk", "talking",
    "q&a", "discussion", "tea time", "recap", "unboxing", "superchat", "free chat",
    "jailbird", "catlord", "schedule", "hrys", "tako time", "bau bau"
]

def is_chatting_stream(title):
    t_lower = title.lower()
    # If explicitly contains watchalong, karaoke, or gameplay title, exclude
    if any(ex in t_lower for ex in EXCLUDE_WORDS):
        return False
    # If contains chat keywords or general title
    if any(cw in t_lower for cw in CHAT_WORDS):
        return True
    # Default fallback: if no explicit game title, consider as potential stream
    return True

def fetch_chatting_vods(vtuber_name, agency, channel_url):
    print(f"Filtering chatting/zatsudan VODs for {vtuber_name}...")
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", "50",
        "--dump-json",
        "--no-warnings",
        channel_url
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not res.stdout.strip():
        return []

    lines = res.stdout.strip().split('\n')
    chat_vods = []
    for line in lines:
        if len(chat_vods) >= 10:
            break
        try:
            item = json.loads(line)
            title = item.get("title", "")
            video_id = item.get("id", "")
            if video_id and not title.startswith("#") and is_chatting_stream(title):
                chat_vods.append({
                    "vtuber": vtuber_name,
                    "agency": agency,
                    "title": title,
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                })
        except Exception:
            continue
    return chat_vods

def main():
    all_candidates = []
    summary_by_vtuber = {}
    
    for name, agency, url in vtubers:
        vods = fetch_chatting_vods(name, agency, url)
        all_candidates.extend(vods)
        summary_by_vtuber[name] = {
            "agency": agency,
            "count": len(vods),
            "titles": [v["title"] for v in vods]
        }
        print(f"✓ [{name}] Found {len(vods)} chatting VODs.")

    with open("scratch/batch_chatting_100.json", "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)

    with open("scratch/summary_chatting.json", "w", encoding="utf-8") as f:
        json.dump(summary_by_vtuber, f, indent=2, ensure_ascii=False)

    print(f"\nCompleted! Total pure chatting streams fetched: {len(all_candidates)}")

if __name__ == "__main__":
    main()
