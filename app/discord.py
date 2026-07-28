from typing import Any

import httpx

from app.logger import discord_logger


async def send_discord_summary_embed(
    webhook_url: str,
    vtuber_name: str,
    agency: str,
    stream_title: str,
    video_id: str,
    thumbnail_url: str,
    duration_seconds: int,
    standout_highlights: list[dict[str, Any]],
    master_summary_snippet: str
) -> bool:
    """Sends a rich Discord embed notification for a completed stream summary."""
    if not webhook_url or not webhook_url.startswith("http"):
        discord_logger.warning("Discord webhook URL is not set or invalid. Skipping Discord alert.")
        return False

    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    duration_mins = f"{round(duration_seconds / 60)} mins" if duration_seconds else "Unknown"

    # Build Highlights text
    highlights_text = ""
    for h in standout_highlights[:5]:
        ts = h.get("timestamp", "00:00:00")
        title = h.get("title", "Highlight")
        highlights_text += f"• **[{ts}]({youtube_url}&t={ts_to_seconds(ts)}s)** - {title}\n"

    embed = {
        "title": f"📺 {stream_title}",
        "url": youtube_url,
        "color": 9127158, # Purple accent color #8b5cf6
        "author": {
            "name": f"{vtuber_name} ({agency})",
            "icon_url": thumbnail_url
        },
        "description": master_summary_snippet[:400] + ("..." if len(master_summary_snippet) > 400 else ""),
        "fields": [
            {
                "name": "⏱️ Duration",
                "value": duration_mins,
                "inline": True
            },
            {
                "name": "⭐ Standout Highlights & Timestamps",
                "value": highlights_text or "No highlights listed.",
                "inline": False
            }
        ],
        "thumbnail": {
            "url": thumbnail_url
        },
        "footer": {
            "text": "VTuber Digest • Automatic Summary Notification"
        }
    }

    payload = {
        "username": "VTuber Digest",
        "avatar_url": "https://raw.githubusercontent.com/mting314/autosub/master/docs/assets/logo.png",
        "embeds": [embed]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(webhook_url, json=payload)
            if res.status_code in (200, 204):
                discord_logger.info(f"Successfully posted Discord embed for stream {video_id}")
                return True
            else:
                discord_logger.error(f"Discord Webhook error ({res.status_code}): {res.text}")
    except Exception as e:
        discord_logger.error(f"Failed to dispatch Discord Webhook: {e}")

    return False

def ts_to_seconds(time_str: str) -> int:
    """Helper to convert HH:MM:SS or MM:SS timestamp string to total seconds for YouTube &t= parameter."""
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        pass
    return 0
