import os
import re
import json
import asyncio
from typing import List, Dict, Any, Tuple
import logging
from dotenv import load_dotenv
from google.genai import types

load_dotenv()

logger = logging.getLogger(__name__)

def get_genai_client():
    from google import genai
    gemini_api_key = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY"))
    gcp_project = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "future-name-201021"))
    gcp_location = os.getenv("GCP_LOCATION", "us-central1")
    
    if gemini_api_key:
        return genai.Client(api_key=gemini_api_key)
    else:
        logger.info(f"Connecting to Vertex AI (Project: {gcp_project}, Location: {gcp_location})")
        return genai.Client(vertexai=True, project=gcp_project, location=gcp_location)

async def summarize_chunk_map(chunk: Dict[str, Any]) -> Dict[str, Any]:
    start_t = chunk["start_time"]
    end_t = chunk["end_time"]
    text = chunk["text"]
    
    prompt = f"""You are an expert VTuber stream analyst summarizing a 15-minute segment of a chatting stream (zatsudan).
Time range: {start_t} - {end_t}

Transcript segment:
{text[:8000]}

Instructions:
1. Summarize all main topics, stories, jokes, lore references, or member interactions in this segment in detail.
2. Extract all hilarious, bizarre, or standout quotes with exact START timestamps (HH:MM:SS format).

CRITICAL TIMESTAMP RULE:
- Always use the exact START timestamp (HH:MM:SS) where a topic, anecdote, or story BEGINS in the transcript.
- NEVER use the middle or end timestamp of a story segment.

Output schema (JSON):
{{
  "time_range": "{start_t} - {end_t}",
  "summary": "Detailed narrative summary of key events and stories discussed",
  "highlights": [
    {{"timestamp": "HH:MM:SS", "topic": "Short title", "description": "Details of the story or funny moment"}}
  ]
}}
"""
    
    try:
        client = get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini API call failed for chunk {start_t}: {e}")
        return {
            "time_range": f"{start_t} - {end_t}",
            "summary": f"Segment from {start_t} to {end_t} discussing stream topics.",
            "highlights": [
                {"timestamp": start_t, "topic": "Stream segment discussion", "description": text[:200] + "..."}
            ]
        }

async def summarize_reduce(vtuber_name: str, stream_title: str, chunk_summaries: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    chunks_str = json.dumps(chunk_summaries, indent=2)
    
    prompt = f"""You are a master Hololive & VTuber content curator summarizing a complete zatsudan stream for "{vtuber_name}".
Stream Title: "{stream_title}"

Here are the 15-minute segment summaries extracted from the stream transcript:
{chunks_str}

Task:
Generate a concise, punchy stream breakdown formatted in Markdown.

CRITICAL INSTRUCTIONS:
- DO NOT start with long, wordy introductory paragraphs or essay-style preamble.
- START IMMEDIATELY with bullet points (TL;DR Quick Summary).
- Keep all bullet points direct, concise, and easy to scan.
- TIMESTAMP ACCURACY: Ensure all story timestamps (HH:MM:SS) represent the exact STARTING moment when a story or topic begins.

Structure:
# {stream_title}

## ⚡ Quick Stream Highlights (TL;DR)
- [Bullet point 1: Key topic/joke/story]
- [Bullet point 2: Key topic/joke/story]
- [Bullet point 3: Key topic/joke/story]
- [Bullet point 4: Key topic/joke/story]

## ⭐ Standout Stories & Timestamps
- **[HH:MM:SS] Title**: Short description of standout story or moment.

## ⏱️ Timeline Breakdown
- **[HH:MM:SS]**: Topic summary

Output schema (JSON):
{{
  "master_summary_markdown": "# Markdown text starting with bullet points...",
  "standout_highlights": [
    {{"timestamp": "HH:MM:SS", "title": "Headline", "description": "Short explanation"}}
  ]
}}
"""

    try:
        client = get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        text_content = response.text.strip()
        match = re.search(r'\{.*\}', text_content, re.DOTALL)
        if match:
            text_content = match.group(0)
            
        parsed = json.loads(text_content, strict=False)
        return parsed.get("master_summary_markdown", ""), parsed.get("standout_highlights", [])
    except Exception as e:
        logger.error(f"Reduce LLM call failed: {e}")
        lines = [f"# {stream_title}\n\n## ⚡ Quick Stream Highlights (TL;DR)\n"]
        highlights = []
        for c in chunk_summaries:
            tr = c.get("time_range", "")
            summ = c.get("summary", "")
            lines.append(f"- **[{tr}]**: {summ[:180]}...")
            for h in c.get("highlights", []):
                highlights.append({
                    "timestamp": h.get("timestamp", tr.split(" - ")[0]),
                    "title": h.get("topic", "Highlight"),
                    "description": h.get("description", "")
                })
        return "\n".join(lines), highlights

async def run_map_reduce_pipeline(vtuber_name: str, stream_title: str, chunks: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Runs parallel chunk Map summaries followed by Reduce master synthesis."""
    logger.info(f"Running Map phase for {len(chunks)} chunks using Vertex AI (project: {GCP_PROJECT})...")
    map_tasks = [summarize_chunk_map(chunk) for chunk in chunks]
    chunk_summaries = await asyncio.gather(*map_tasks)
    
    logger.info("Running Reduce phase for master synthesis...")
    master_summary, standout_highlights = await summarize_reduce(vtuber_name, stream_title, chunk_summaries)
    
    return master_summary, standout_highlights, chunk_summaries
