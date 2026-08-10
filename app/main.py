import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.database import get_session, init_db
from app.discord import send_discord_summary_embed
from app.ingestion import parse_youtube_atom_feed, poll_channel_rss
from app.logger import ingestion_logger, manual_logger, pipeline_logger
from app.models import JobStatus, Stream, Summary, UserSettings, VTuber
from app.storage import storage_manager
from app.summarizer import run_map_reduce_pipeline
from app.transcriber import chunk_cues, download_youtube_subtitles, parse_vtt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VTuber Digest", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

def _cache_version() -> str:
    """Content hash of app.js so a changed bundle busts the browser cache."""
    try:
        with open("app/static/app.js", "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except FileNotFoundError:
        return "dev"


@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    return html.replace("__CACHE_VERSION__", _cache_version())

# --- Periodic RSS Poller Loop ---
async def background_rss_poller():
    """Periodic background task that polls RSS feeds for all tracked VTubers every 30 minutes."""
    while True:
        try:
            logger.info("Running periodic background RSS poll for tracked VTubers...")
            with next(get_session()) as session:
                vtubers = session.exec(select(VTuber)).all()
                for vtuber in vtubers:
                    entries = await poll_channel_rss(vtuber.channel_id)
                    for entry in entries:
                        video_id = entry["video_id"]
                        existing = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
                        if not existing:
                            stream = Stream(
                                video_id=video_id,
                                title=entry["title"],
                                published_at=datetime.utcnow(),
                                thumbnail_url=entry["thumbnail_url"],
                                status=JobStatus.PENDING,
                                vtuber_id=vtuber.id
                            )
                            session.add(stream)
                            session.commit()
                            session.refresh(stream)
                            
                            logger.info(f"Background RSS poller discovered new VOD: {video_id} for {vtuber.name}")
                            asyncio.create_task(process_stream_pipeline(stream.id))
        except Exception as e:
            logger.error(f"Error in background RSS poller loop: {e}")
            
        await asyncio.sleep(300) # Poll every 5 minutes for real-time stream ingestion right when streams end

@app.on_event("startup")
def on_startup():
    # Architecture A (read-only gallery): summaries are produced by the batch
    # ingest job (scratch/ingest_single_stream.py) and served as static JSON.
    # This local DB is a transient build/dev store only — no runtime GCS sync.
    init_db()
    # Seed default VTubers if empty or fix invalid legacy channel IDs
    valid_channel_ids = {
        "Shiori Novella": "UCgnfPPb9JI3e9A4cXHnWbyg",
        "Kobo Kanaeru": "UCjLEmnpCNeisMxy134KPwWw",
        "Nerissa Ravencroft": "UC_sFNM0z0MWm9A6WlKPuMMg",
        "Vestia Zeta": "UCTvHWSfBZgtxE4sILOaurIQ",
        "Zeta Vestia": "UCTvHWSfBZgtxE4sILOaurIQ",
        "Ironmouse": "UCj_TYZ60NDQYY5QpUvOge9g",
        "Gawr Gura": "UCoSrY_IQQVpmIRZ9Xf-y93g",
        "FUWAMOCO": "UCt9H_RpQzhxzlyBxFqrdHqA",
    }
    with next(get_session()) as session:
        existing = session.exec(select(VTuber)).all()
        if not existing:
            default_vtubers = [
                VTuber(name="Shiori Novella", channel_id="UCgnfPPb9JI3e9A4cXHnWbyg", agency="Hololive English"),
                VTuber(name="Kobo Kanaeru", channel_id="UCjLEmnpCNeisMxy134KPwWw", agency="Hololive ID"),
                VTuber(name="Nerissa Ravencroft", channel_id="UC_sFNM0z0MWm9A6WlKPuMMg", agency="Hololive English"),
                VTuber(name="Vestia Zeta", channel_id="UCTvHWSfBZgtxE4sILOaurIQ", agency="Hololive ID"),
                VTuber(name="Ironmouse", channel_id="UCj_TYZ60NDQYY5QpUvOge9g", agency="VShojo"),
                VTuber(name="Gawr Gura", channel_id="UCoSrY_IQQVpmIRZ9Xf-y93g", agency="Hololive English"),
                VTuber(name="FUWAMOCO", channel_id="UCt9H_RpQzhxzlyBxFqrdHqA", agency="Hololive English"),
            ]
            for v in default_vtubers:
                session.add(v)
            session.commit()
            logger.info("Seeded initial VTubers into database.")
        else:
            for v in existing:
                if v.name in valid_channel_ids and v.channel_id != valid_channel_ids[v.name]:
                    v.channel_id = valid_channel_ids[v.name]
                    session.add(v)
            session.commit()
            
    # Start background RSS poller loop
    asyncio.create_task(background_rss_poller())

# --- Background Task Pipeline ---
async def process_stream_pipeline(stream_id: int):
    pipeline_logger.info(f"[Stream {stream_id}] Pipeline started.")
    with next(get_session()) as session:
        stream = session.get(Stream, stream_id)
        if not stream:
            pipeline_logger.error(f"[Stream {stream_id}] Aborting: stream row not found.")
            return

        stream.status = JobStatus.FETCHING_TRANSCRIPT
        video_id = stream.video_id
        session.add(stream)
        session.commit()
    pipeline_logger.info(f"[Stream {stream_id}] Status -> FETCHING_TRANSCRIPT for video_id={video_id}.")

    try:
        # Step 1: Download Subtitles via yt-dlp
        pipeline_logger.info(f"[Stream {stream_id}] Downloading subtitles via yt-dlp...")
        vtt_text, meta = download_youtube_subtitles(video_id)

        if not vtt_text:
            fail_msg = "No auto-captions or subtitles available yet."
            pipeline_logger.warning(f"[Stream {stream_id}] Status -> FAILED: {fail_msg} (video_id={video_id})")
            with next(get_session()) as session:
                stream = session.get(Stream, stream_id)
                stream.status = JobStatus.FAILED
                stream.error_message = fail_msg
                session.add(stream)
                session.commit()
            return
            
        # Save raw transcript to GCS (or local storage fallback)
        gcs_uri = storage_manager.save_transcript(video_id, vtt_text)
        pipeline_logger.info(f"[Stream {stream_id}] Transcript saved to {gcs_uri}.")

        # Step 2: Parse VTT and Chunk into 15-min intervals
        cues = parse_vtt(vtt_text)
        chunks = chunk_cues(cues, interval_minutes=15)
        pipeline_logger.info(f"[Stream {stream_id}] Parsed {len(cues)} cues into {len(chunks)} chunks.")

        # Step 3: Run Map-Reduce LLM Summarizer
        pipeline_logger.info(f"[Stream {stream_id}] Status -> SUMMARIZING (Map-Reduce over {len(chunks)} chunks).")
        with next(get_session()) as session:
            stream = session.get(Stream, stream_id)
            stream.status = JobStatus.SUMMARIZING
            if meta.get('title'):
                stream.title = meta['title']
            if meta.get('duration'):
                stream.duration_seconds = int(meta['duration'])
            session.add(stream)
            session.commit()
            
            vtuber_name = stream.vtuber.name if stream.vtuber else "VTuber"
            stream_title = stream.title
            
        master_summary, standout_highlights, chunk_summaries, stream_category = await run_map_reduce_pipeline(
            vtuber_name=vtuber_name,
            stream_title=stream_title,
            chunks=chunks
        )
        
        # Check for non-blocking issue if 0 highlights extracted
        warning_msg = None
        if not standout_highlights:
            warning_msg = "No standout story highlights detected. Stream may be low-speech or extended gameplay."
            pipeline_logger.warning(f"Non-blocking warning for Stream ID {stream_id} ({video_id}): {warning_msg}")

        # Step 4: Save Summary & Update Stream Status
        with next(get_session()) as session:
            stream = session.get(Stream, stream_id)
            stream.status = JobStatus.COMPLETED
            stream.stream_category = stream_category
            stream.gcs_transcript_uri = gcs_uri
            stream.warning_message = warning_msg
            
            summary_obj = Summary(
                stream_id=stream.id,
                master_summary=master_summary,
                standout_highlights_json=json.dumps(standout_highlights),
                chunk_data_json=json.dumps(chunk_summaries)
            )
            session.add(summary_obj)
            session.add(stream)
            session.commit()
            
            # Fetch user settings for Discord Webhook
            settings = session.exec(select(UserSettings).where(UserSettings.id == 1)).first()
            if settings and settings.is_discord_enabled and settings.discord_webhook_url:
                muted_agencies = json.loads(settings.muted_agencies_json or "[]")
                vtuber_agency = stream.vtuber.agency if stream.vtuber else ""
                if vtuber_agency not in muted_agencies:
                    pipeline_logger.info(f"Dispatching Discord webhook for stream {video_id}...")
                    await send_discord_summary_embed(
                        webhook_url=settings.discord_webhook_url,
                        vtuber_name=stream.vtuber.name if stream.vtuber else "VTuber",
                        agency=vtuber_agency,
                        stream_title=stream.title,
                        video_id=stream.video_id,
                        thumbnail_url=stream.thumbnail_url,
                        duration_seconds=stream.duration_seconds,
                        standout_highlights=standout_highlights,
                        master_summary_snippet=master_summary
                    )
            
        pipeline_logger.info(f"Successfully processed summary for Stream ID: {stream_id} ({stream_title})")

    except Exception as e:
        pipeline_logger.error(f"Pipeline error for Stream ID {stream_id}: {e}", exc_info=True)
        with next(get_session()) as session:
            stream = session.get(Stream, stream_id)
            stream.status = JobStatus.FAILED
            stream.error_message = str(e)
            session.add(stream)
            session.commit()

# --- WebSub & Trigger Endpoints ---
@app.get("/api/webhooks/youtube")
def youtube_webhook_verify(request: Request):
    challenge = request.query_params.get("hub.challenge")
    if challenge:
        return Response(content=challenge, media_type="text/plain")
    return Response(content="WebSub handler", media_type="text/plain")

@app.post("/api/webhooks/youtube")
async def youtube_webhook_handler(request: Request, bg_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    body_text = (await request.body()).decode("utf-8")
    ingestion_logger.info("Received incoming WebSub push notification from YouTube.")
    entries = parse_youtube_atom_feed(body_text)
    
    triggered_streams = []
    for entry in entries:
        video_id = entry["video_id"]
        existing = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
        if not existing:
            vtuber = session.exec(select(VTuber).where(VTuber.channel_id == entry["channel_id"])).first()
            stream = Stream(
                video_id=video_id,
                title=entry["title"],
                published_at=datetime.utcnow(),
                thumbnail_url=entry["thumbnail_url"],
                status=JobStatus.PENDING,
                vtuber_id=vtuber.id if vtuber else None
            )
            session.add(stream)
            session.commit()
            session.refresh(stream)
            
            ingestion_logger.info(f"WebSub queued new stream: {video_id} ({entry['title']})")
            bg_tasks.add_task(process_stream_pipeline, stream.id)
            triggered_streams.append(video_id)
            
    return {"message": "Webhook processed", "triggered": triggered_streams}

@app.post("/api/streams/trigger")
async def manual_trigger_stream(payload: dict, bg_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    url = payload.get("url", "").strip()
    manual_logger.info(f"Manual stream submission request for URL: {url}")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
        
    match = re.search(r'(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})', url)
    if not match:
        manual_logger.warning(f"Invalid YouTube URL submission: {url}")
        raise HTTPException(status_code=400, detail="Invalid YouTube URL format")
        
    video_id = match.group(1)
    
    existing = session.exec(select(Stream).where(Stream.video_id == video_id)).first()
    if existing:
        if existing.status == JobStatus.FAILED:
            existing.status = JobStatus.PENDING
            existing.error_message = None
            session.add(existing)
            session.commit()
            manual_logger.info(f"Re-triggered failed stream summary for {video_id}")
            bg_tasks.add_task(process_stream_pipeline, existing.id)
            return {"message": "Re-triggered failed stream summary", "stream_id": existing.id}
        return {"message": "Stream summary already exists or in progress", "stream_id": existing.id}
        
    stream = Stream(
        video_id=video_id,
        title=f"YouTube Stream ({video_id})",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        status=JobStatus.PENDING,
    )
    session.add(stream)
    session.commit()
    session.refresh(stream)
    
    manual_logger.info(f"Queued manual stream summary for video_id: {video_id}")
    bg_tasks.add_task(process_stream_pipeline, stream.id)
    return {"message": "Stream summary job queued", "stream_id": stream.id, "video_id": video_id}

# --- Settings & User Personalization Endpoints ---
@app.get("/api/settings")
def get_user_settings(session: Session = Depends(get_session)):
    settings = session.exec(select(UserSettings).where(UserSettings.id == 1)).first()
    if not settings:
        settings = UserSettings(id=1, is_discord_enabled=True, summary_style="bullet_first", muted_agencies_json="[]")
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return {
        "id": settings.id,
        "discord_webhook_url": settings.discord_webhook_url,
        "is_discord_enabled": settings.is_discord_enabled,
        "summary_style": settings.summary_style,
        "muted_agencies": json.loads(settings.muted_agencies_json or "[]")
    }

@app.put("/api/settings")
def update_user_settings(payload: dict, session: Session = Depends(get_session)):
    settings = session.exec(select(UserSettings).where(UserSettings.id == 1)).first()
    if not settings:
        settings = UserSettings(id=1)
        
    if "discord_webhook_url" in payload:
        settings.discord_webhook_url = payload["discord_webhook_url"]
    if "is_discord_enabled" in payload:
        settings.is_discord_enabled = bool(payload["is_discord_enabled"])
    if "summary_style" in payload:
        settings.summary_style = payload["summary_style"]
    if "muted_agencies" in payload:
        settings.muted_agencies_json = json.dumps(payload["muted_agencies"])
        
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return {"message": "Settings updated successfully"}

# --- Search & Retrieval Endpoints ---
@app.get("/api/streams")
def list_streams(
    agency: str | None = None,
    category: str | None = None,
    vtuber_id: int | None = None,
    q: str | None = None,
    session: Session = Depends(get_session)
):
    query = select(Stream)
    
    if vtuber_id:
        query = query.where(Stream.vtuber_id == vtuber_id)
        
    if agency:
        query = query.join(VTuber).where(VTuber.agency == agency)

    if category:
        query = query.where(Stream.stream_category == category)
        
    streams = session.exec(query.order_by(Stream.published_at.desc())).all()
    
    result = []
    for s in streams:
        summary_obj = s.summary
        has_summary = summary_obj is not None
        
        # Client query text search filter
        if q and q.lower() not in s.title.lower():
            if not (has_summary and q.lower() in summary_obj.master_summary.lower()):
                continue
                
        result.append({
            "id": s.id,
            "video_id": s.video_id,
            "title": s.title,
            "duration_seconds": s.duration_seconds,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "thumbnail_url": s.thumbnail_url,
            "status": s.status,
            "stream_category": s.stream_category or "chatting",
            "error_message": s.error_message,
            "warning_message": s.warning_message,
            "vtuber": {
                "id": s.vtuber.id,
                "name": s.vtuber.name,
                "agency": s.vtuber.agency
            } if s.vtuber else None,
            "has_summary": has_summary
        })
        
    return result

@app.get("/api/streams/{stream_id}")
def get_stream_detail(stream_id: int, session: Session = Depends(get_session)):
    stream = session.get(Stream, stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
        
    summary_obj = stream.summary
    
    return {
        "id": stream.id,
        "video_id": stream.video_id,
        "title": stream.title,
        "duration_seconds": stream.duration_seconds,
        "published_at": stream.published_at.isoformat() if stream.published_at else None,
        "thumbnail_url": stream.thumbnail_url,
        "status": stream.status,
        "stream_category": stream.stream_category or "chatting",
        "error_message": stream.error_message,
        "warning_message": stream.warning_message,
        "gcs_transcript_uri": stream.gcs_transcript_uri,
        "vtuber": {
            "id": stream.vtuber.id,
            "name": stream.vtuber.name,
            "agency": stream.vtuber.agency
        } if stream.vtuber else None,
        "summary": {
            "master_summary": summary_obj.master_summary if summary_obj else None,
            "standout_highlights": json.loads(summary_obj.standout_highlights_json) if summary_obj else [],
            "chunks": json.loads(summary_obj.chunk_data_json) if summary_obj else []
        } if summary_obj else None
    }

@app.get("/api/vtubers")
def list_vtubers(session: Session = Depends(get_session)):
    return session.exec(select(VTuber)).all()

@app.post("/api/vtubers")
def add_vtuber(payload: dict, session: Session = Depends(get_session)):
    vtuber = VTuber(
        name=payload["name"],
        channel_id=payload["channel_id"],
        agency=payload.get("agency", "Indies"),
        avatar_url=payload.get("avatar_url")
    )
    session.add(vtuber)
    session.commit()
    session.refresh(vtuber)
    return vtuber
