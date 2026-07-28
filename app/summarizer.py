import asyncio
import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
from google.genai import types
from pydantic import BaseModel, Field

from app.glossary import VTUBER_GLOSSARY_PROMPT, normalize_vtuber_transcript_text

load_dotenv()

logger = logging.getLogger(__name__)

GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "vtuber-digest-503801"))
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")

def get_genai_client():
    from google import genai
    gemini_api_key = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY"))
    
    if gemini_api_key:
        return genai.Client(api_key=gemini_api_key)
    else:
        logger.info(f"Connecting to Vertex AI (Project: {GCP_PROJECT}, Location: {GCP_LOCATION})")
        return genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)


class MapHighlightItem(BaseModel):
    timestamp: str = Field(description="Exact START timestamp in HH:MM:SS format")
    topic: str = Field(description="Short headline title")
    description: str = Field(description="Details of the story or moment")

class MapChunkResponse(BaseModel):
    time_range: str = Field(description="Start time - End time range")
    summary: str = Field(description="Detailed narrative summary of this segment")
    highlights: list[MapHighlightItem] = Field(default_factory=list)

class StandoutHighlight(BaseModel):
    timestamp: str = Field(description="Exact START timestamp in HH:MM:SS format")
    title: str = Field(description="Headline title of the story or moment")
    description: str = Field(description="Explanation of what happened")

class TimelineEntry(BaseModel):
    timestamp: str = Field(description="Exact START timestamp in HH:MM:SS format")
    title: str = Field(description="Short 2-5 word headline topic title in Title Case (e.g. Doraemon Bully Critique)")
    details: str = Field(description="Detailed description of discussions, lore, or stories in this segment")

class MasterSummaryResponse(BaseModel):
    quick_highlights_tldr: list[str] = Field(description="3-5 executive bullet points summarizing main takeaways (NO timestamps allowed here)")
    standout_stories: list[StandoutHighlight] = Field(description="Standout stories with exact START timestamps")
    timeline_breakdown: list[TimelineEntry] = Field(description="Chronological 15-minute topic breakdown with bold titles")

def build_standardized_markdown(vtuber_name: str, stream_title: str, data: MasterSummaryResponse) -> str:
    """Deterministically renders Pydantic response into guaranteed, standardized Markdown."""
    lines = [f"# {stream_title}\n"]
    
    # 1. Quick Stream Highlights (TL;DR) - NO Timestamps
    lines.append("## ⚡ Quick Stream Highlights (TL;DR)")
    for item in data.quick_highlights_tldr:
        clean_item = re.sub(r'^\s*[\-\*•]?\s*(\[\d{1,2}:\d{2}(:\d{2})?\]\s*)?', '', item).strip()
        if clean_item:
            lines.append(f"- {clean_item}")
    lines.append("")
    
    # 2. Standout Stories & Timestamps - Mandatory [HH:MM:SS] Title
    lines.append("## ⭐ Standout Stories & Timestamps")
    for story in data.standout_stories:
        ts = story.timestamp.strip() if story.timestamp else "00:00:00"
        title = story.title.strip()
        desc = story.description.strip()
        lines.append(f"- **[{ts}] {title}**: {desc}")
    lines.append("")
    
    # 3. Timeline Breakdown - Mandatory [HH:MM:SS] Bold Title: Details
    lines.append("## ⏱️ Timeline Breakdown")
    for entry in data.timeline_breakdown:
        ts = entry.timestamp.strip() if entry.timestamp else "00:00:00"
        title = entry.title.strip() if entry.title else "Stream Topic"
        details = entry.details.strip() if entry.details else ""
        lines.append(f"- **[{ts}] {title}**: {details}")
        
    raw_markdown = "\n".join(lines)
    if vtuber_name:
        # Enforce VTuber name usage over generic pronouns / terms
        raw_markdown = re.sub(r'\b[Tt]he [Vv][Tt]uber\b', vtuber_name, raw_markdown)
        raw_markdown = re.sub(r'\b[Tt]he [Ss]treamer\b', vtuber_name, raw_markdown)
        raw_markdown = re.sub(r'\b[Tt]he [Ss]peaker\b', vtuber_name, raw_markdown)
    return raw_markdown


async def summarize_chunk_map(chunk: dict[str, Any]) -> dict[str, Any]:
    start_t = chunk["start_time"]
    end_t = chunk["end_time"]
    text = chunk["text"]
    
    # Pre-process transcript text with VTuber name dictionary
    clean_text = normalize_vtuber_transcript_text(text)
    
    prompt = f"""{VTUBER_GLOSSARY_PROMPT}

You are an expert VTuber stream analyst summarizing a 15-minute segment of a chatting stream (zatsudan).
Time range: {start_t} - {end_t}

Transcript segment:
{clean_text[:8000]}

Instructions:
1. Summarize all main topics, stories, jokes, lore references, or member interactions in this segment.
2. Extract standout moments with exact START timestamps.

CRITICAL NOISE & INTRO SUPPRESSION RULE:
- Completely IGNORE stream starting BGM, "stream starting soon" waiting screens, opening music, screams, or "Yippee" intro exclamations.
- DO NOT mention opening music or intro screens.

CRITICAL TIMESTAMP RULE:
- Always use the exact START timestamp ({start_t} or where a topic BEGINS at the start of that segment's transcript). DO NOT use the timestamp of the last line.
"""
    
    try:
        client = get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MapChunkResponse
            )
        )
        parsed = MapChunkResponse.model_validate_json(response.text)
        return parsed.model_dump()
    except Exception as e:
        logger.error(f"Gemini API call failed for chunk {start_t}: {e}")
        return {
            "time_range": f"{start_t} - {end_t}",
            "summary": f"Segment from {start_t} to {end_t} discussing stream topics.",
            "highlights": [
                {"timestamp": start_t, "topic": "Stream segment discussion", "description": clean_text[:200] + "..."}
            ]
        }

async def summarize_reduce(vtuber_name: str, stream_title: str, chunk_summaries: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    chunks_str = json.dumps(chunk_summaries, indent=2)
    
    prompt = f"""{VTUBER_GLOSSARY_PROMPT}

You are a master Hololive & VTuber content curator summarizing a complete zatsudan stream for "{vtuber_name}".
Stream Title: "{stream_title}"

Here are the 15-minute segment summaries extracted from the stream transcript:
{chunks_str}

Task:
Extract executive quick highlights, standout stories, and chronological timeline entries.

CRITICAL RULES:
1. STRICT NAMING CONVENTION: NEVER refer to {vtuber_name} as "the streamer", "the VTuber", "she", or "they". ALWAYS refer to them explicitly by their actual name "{vtuber_name}" in all highlights, titles, and descriptions.
2. NO INTRO MUSIC: Completely IGNORE opening BGM, waiting screens, or intro screams/Yippees. Start directly with actual conversational topics.
3. PROPER NOUN CORRECTION: Strictly verify all VTuber names against the dictionary above (e.g. "Ouro Kronii" / "Kronii", NOT "Crony").
4. quick_highlights_tldr: Provide 3-5 high-level executive summary bullet points. DO NOT include timestamps here.
5. standout_stories: List 4-8 standout stories with exact START timestamps (HH:MM:SS) and catchy titles.
6. timeline_breakdown: List chronological 15-minute segment entries with exact START timestamps (HH:MM:SS), a short 2-5 word bold headline title (e.g. "Doraemon Bully Critique"), and segment details.
"""

    try:
        client = get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MasterSummaryResponse
            )
        )
        parsed = MasterSummaryResponse.model_validate_json(response.text)
        
        # Deterministically build standardized Markdown from validated Pydantic model
        master_markdown = build_standardized_markdown(vtuber_name, stream_title, parsed)
        standout_highlights = [h.model_dump() for h in parsed.standout_stories]
        
        return master_markdown, standout_highlights
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
                    "timestamp": h.get("timestamp", tr),
                    "title": h.get("topic", "Highlight"),
                    "description": h.get("description", "")
                })
        return "\n".join(lines), highlights

async def run_map_reduce_pipeline(vtuber_name: str, stream_title: str, chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Runs parallel chunk Map summaries followed by Reduce master synthesis."""
    logger.info(f"Running Map phase for {len(chunks)} chunks using Vertex AI (project: {GCP_PROJECT})...")
    map_tasks = [summarize_chunk_map(chunk) for chunk in chunks]
    chunk_summaries = await asyncio.gather(*map_tasks)
    
    logger.info("Running Reduce phase for master synthesis...")
    master_summary, standout_highlights = await summarize_reduce(vtuber_name, stream_title, chunk_summaries)
    
    return master_summary, standout_highlights, chunk_summaries
