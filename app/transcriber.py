import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class Cue:
    def __init__(self, start_sec: int, time_str: str, text: str):
        self.start_sec = start_sec
        self.time_str = time_str
        self.text = text

def download_youtube_subtitles(video_id: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Downloads YouTube English/auto-subtitles for a video using yt-dlp.
    Returns (vtt_content, metadata_dict).
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_tmpl = str(Path(temp_dir) / "%(id)s")
        cmd = [
            "yt-dlp",
            "--write-auto-subs",
            "--sub-lang", "en",
            "--skip-download",
            "--dump-json",
            "-o", output_tmpl,
            video_url
        ]
        
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            meta = {}
            if res.stdout:
                import json
                try:
                    meta = json.loads(res.stdout.strip().split('\n')[0])
                except Exception:
                    pass
            
            # Find generated .vtt file
            vtt_files = list(Path(temp_dir).glob("*.vtt"))
            if vtt_files:
                vtt_content = vtt_files[0].read_text(encoding="utf-8")
                return vtt_content, meta
            else:
                logger.warning(f"No VTT subtitle files found for {video_id}")
                return None, meta
        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlp failed for {video_id}: {e.stderr}")
            return None, {}

def parse_vtt(vtt_content: str) -> List[Cue]:
    """Parses raw VTT text into clean Cue objects, stripping tags and duplicate lines."""
    lines = vtt_content.splitlines()
    cues: List[Cue] = []
    
    time_pattern = re.compile(r'(\d+:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3}) -->')
    curr_time = "00:00:00"
    curr_sec = 0
    seen_lines = set()
    
    for line in lines:
        m = time_pattern.search(line)
        if m:
            raw_t = m.group(1).split('.')[0]
            parts = raw_t.split(':')
            if len(parts) == 3:
                curr_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                curr_time = raw_t
            elif len(parts) == 2:
                curr_sec = int(parts[0]) * 60 + int(parts[1])
                curr_time = f"00:{raw_t}"
        elif line.strip() and not line.startswith('WEBVTT') and not line.startswith('Kind:') and not line.startswith('Language:'):
            clean_text = re.sub(r'<[^>]+>', '', line.strip())
            if clean_text and clean_text not in seen_lines:
                seen_lines.add(clean_text)
                cues.append(Cue(start_sec=curr_sec, time_str=curr_time, text=clean_text))
                
    return cues

def chunk_cues(cues: List[Cue], interval_minutes: int = 15) -> List[Dict[str, Any]]:
    """Groups cues into interval_minutes chunk blocks (e.g. 0-15m, 15-30m) for Map-Reduce processing."""
    interval_secs = interval_minutes * 60
    buckets: Dict[int, List[Cue]] = {}
    
    for cue in cues:
        b_idx = cue.start_sec // interval_secs
        if b_idx not in buckets:
            buckets[b_idx] = []
        buckets[b_idx].append(cue)
        
    chunks = []
    for b_idx in sorted(buckets.keys()):
        c_list = buckets[b_idx]
        if not c_list:
            continue
            
        start_t = c_list[0].time_str
        end_t = c_list[-1].time_str
        full_text = " ".join([c.text for c in c_list])
        
        chunks.append({
            "chunk_index": b_idx,
            "start_time": start_t,
            "end_time": end_t,
            "start_sec": b_idx * interval_secs,
            "text": full_text
        })
        
    return chunks
