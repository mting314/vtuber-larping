import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015'
}

STRICT_CHAT_KEYWORDS = [
    "chat", "chatting", "zatsudan", "雑談", "free chat", "rambles", "rambling",
    "talk", "talking", "q&a", "discussion", "tea time", "recap", "unboxing",
    "schedule", "superchat", "jailbird", "catlord", "hrys", "tako time", "bau bau"
]

STRICT_NON_CHAT_KEYWORDS = [
    "zelda", "wind waker", "mario", "pokemon", "minecraft", "valorant", "apex",
    "elden ring", "dark souls", "resident evil", "palworld", "overcooked",
    "phasmophobia", "lethal company", "vrchat", "pratfall", "poppucom",
    "assassin", "creed", "black flag", "gta", "grand theft auto", "final fantasy",
    "monster hunter", "genshin", "starrail", "honkai", "wuthering", "cyberpunk",
    "hollow knight", "silksong", "donkey kong", "metroid", "sonic", "halo",
    "watchalong", "movie", "karaoke", "concert", "3d live", "mini live",
    "gameplay", "playthrough", "cover", "original song", "#shorts"
]

def is_strict_chatting_stream(title: str) -> bool:
    """Returns True if the title indicates a genuine chatting / zatsudan stream."""
    t_lower = title.lower()
    if any(k in t_lower for k in STRICT_NON_CHAT_KEYWORDS):
        return False
    if any(k in t_lower for k in STRICT_CHAT_KEYWORDS):
        return True
    return False

def parse_youtube_atom_feed(xml_content: str) -> list[dict[str, Any]]:
    """Parses YouTube Atom XML feed string and returns list of video objects."""
    entries = []
    try:
        root = ET.fromstring(xml_content)
        for entry in root.findall('atom:entry', NAMESPACES):
            video_id_elem = entry.find('yt:videoId', NAMESPACES)
            title_elem = entry.find('atom:title', NAMESPACES)
            published_elem = entry.find('atom:published', NAMESPACES)
            channel_id_elem = entry.find('yt:channelId', NAMESPACES)
            author_name_elem = entry.find('atom:author/atom:name', NAMESPACES)
            
            title_text = title_elem.text if title_elem is not None else ''
            
            if video_id_elem is not None and video_id_elem.text and is_strict_chatting_stream(title_text):
                entries.append({
                    'video_id': video_id_elem.text,
                    'title': title_text,
                    'published_at': published_elem.text if published_elem is not None else '',
                    'channel_id': channel_id_elem.text if channel_id_elem is not None else '',
                    'channel_name': author_name_elem.text if author_name_elem is not None else '',
                    'thumbnail_url': f"https://i.ytimg.com/vi/{video_id_elem.text}/hqdefault.jpg"
                })
    except Exception as e:
        logger.error(f"Error parsing YouTube Atom XML feed: {e}")
        
    return entries

async def poll_channel_rss(channel_id: str) -> list[dict[str, Any]]:
    """Fetches public RSS XML feed for a YouTube channel without consuming API quota."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                return parse_youtube_atom_feed(res.text)
        except Exception as e:
            logger.error(f"Failed to fetch RSS for channel {channel_id}: {e}")
            
    return []
