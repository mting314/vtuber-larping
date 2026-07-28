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

from pydantic import BaseModel, Field

class MapHighlightItem(BaseModel):
    timestamp: str = Field(description="Exact START timestamp in HH:MM:SS format")
    topic: str = Field(description="Short headline title")
    description: str = Field(description="Details of the story or moment")

class MapChunkResponse(BaseModel):
    time_range: str = Field(description="Start time - End time range")
    summary: str = Field(description="Detailed narrative summary of this segment")
    highlights: List[MapHighlightItem] = Field(default_factory=list)

class StandoutHighlight(BaseModel):
    timestamp: str = Field(description="Exact START timestamp in HH:MM:SS format")
    title: str = Field(description="Headline title of the story or moment")
    description: str = Field(description="Explanation of what happened")

class TimelineEntry(BaseModel):
    timestamp: str = Field(description="START timestamp in HH:MM:SS format")
    summary: str = Field(description="Chronological segment topic summary")

class MasterSummaryResponse(BaseModel):
    quick_highlights_tldr: List[str] = Field(description="3-5 executive bullet points summarizing main takeaways (NO timestamps allowed here)")
    standout_stories: List[StandoutHighlight] = Field(description="Standout stories with exact START timestamps")
    timeline_breakdown: List[TimelineEntry] = Field(description="Chronological 15-minute topic breakdown")

def build_standardized_markdown(vtuber_name: str, stream_title: str, data: MasterSummaryResponse) -> str:
    """Deterministically renders Pydantic response into guaranteed, standardized Markdown."""
    lines = [f"# {stream_title}\n"]
    
    # 1. Quick Stream Highlights (TL;DR) - NO Timestamps
    lines.append("## ⚡ Quick Stream Highlights (TL;DR)")
    for item in data.quick_highlights_tldr:
        # Strip any accidental leading timestamps or bullet markers
        clean_item = re.sub(r'^\s*[\-\*•]?\s*(\[\d{1,2}:\d{2}(:\d{2})?\]\s*)?', '', item).strip()
        if clean_item:
            if not clean_item.startswith("**"):
                lines.append(f"- {clean_item}")
            else:
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
    
    # 3. Timeline Breakdown - Mandatory [HH:MM:SS]
    lines.append("## ⏱️ Timeline Breakdown")
    for entry in data.timeline_breakdown:
        ts = entry.timestamp.strip() if entry.timestamp else "00:00:00"
        summ = entry.summary.strip()
        lines.append(f"- **[{ts}]**: {summ}")
        
    return "\n".join(lines)

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
Extract executive quick highlights, standout stories, and chronological timeline entries.

CRITICAL RULES:
1. quick_highlights_tldr: Provide 3-5 high-level executive summary bullet points. DO NOT include timestamps here.
2. standout_stories: List 4-8 standout stories with exact START timestamps (HH:MM:SS).
3. timeline_breakdown: List chronological 15-minute segment summaries with START timestamps (HH:MM:SS).
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

async def run_map_reduce_pipeline(vtuber_name: str, stream_title: str, chunks: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Runs parallel chunk Map summaries followed by Reduce master synthesis."""
    logger.info(f"Running Map phase for {len(chunks)} chunks using Vertex AI (project: {GCP_PROJECT})...")
    map_tasks = [summarize_chunk_map(chunk) for chunk in chunks]
    chunk_summaries = await asyncio.gather(*map_tasks)
    
    logger.info("Running Reduce phase for master synthesis...")
    master_summary, standout_highlights = await summarize_reduce(vtuber_name, stream_title, chunk_summaries)
    
    return master_summary, standout_highlights, chunk_summaries
