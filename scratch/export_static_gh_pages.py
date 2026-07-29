import json
import os
import shutil
import sys

from sqlmodel import Session, select

from app.database import engine, init_db
from app.models import JobStatus, Stream, VTuber

sys.stdout.reconfigure(encoding='utf-8')

def export_static_site():
    dist_dir = "dist"
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
        
    os.makedirs(f"{dist_dir}/api/streams", exist_ok=True)
    os.makedirs(f"{dist_dir}/static", exist_ok=True)

    print("=== Exporting VTuber Digest for GitHub Pages ===")
    init_db()

    with Session(engine) as session:
        vtubers = session.exec(select(VTuber)).all()
        streams = session.exec(select(Stream).where(Stream.status == JobStatus.COMPLETED)).all()

        # 1. Export VTubers JSON
        vtubers_data = [
            {"id": v.id, "name": v.name, "agency": v.agency, "channel_id": v.channel_id}
            for v in vtubers
        ]
        with open(f"{dist_dir}/api/vtubers.json", "w", encoding="utf-8") as f:
            json.dump(vtubers_data, f, indent=2, ensure_ascii=False)

        # 2. Export Streams List JSON & Stream Details JSON
        streams_list = []
        for s in streams:
            summary_obj = s.summary
            has_summary = summary_obj is not None
            
            stream_dict = {
                "id": s.id,
                "video_id": s.video_id,
                "title": s.title,
                "duration_seconds": s.duration_seconds,
                "published_at": s.published_at.isoformat() if s.published_at else None,
                "thumbnail_url": s.thumbnail_url,
                "status": s.status,
                "stream_category": getattr(s, "stream_category", None) or "chatting",
                "error_message": s.error_message,
                "warning_message": s.warning_message,
                "vtuber": {
                    "id": s.vtuber.id,
                    "name": s.vtuber.name,
                    "agency": s.vtuber.agency
                } if s.vtuber else None,
                "has_summary": has_summary
            }
            streams_list.append(stream_dict)

            # Export individual stream detail JSON for modal view
            detail_dict = dict(stream_dict)
            detail_dict["summary"] = {
                "master_summary": summary_obj.master_summary if summary_obj else None,
                "standout_highlights": json.loads(summary_obj.standout_highlights_json) if summary_obj else [],
                "chunks": json.loads(summary_obj.chunk_data_json) if summary_obj else []
            } if summary_obj else None

            with open(f"{dist_dir}/api/streams/{s.id}.json", "w", encoding="utf-8") as f:
                json.dump(detail_dict, f, indent=2, ensure_ascii=False)

        with open(f"{dist_dir}/api/streams.json", "w", encoding="utf-8") as f:
            json.dump(streams_list, f, indent=2, ensure_ascii=False)

    # 3. Copy static JS bundle and inject a content-hash cache buster.
    # The bundle URL is what the browser keys its cache on, so hashing the
    # file contents guarantees a changed bundle is always refetched while an
    # unchanged one stays cached.
    import hashlib

    with open("app/static/app.js", "rb") as f:
        app_js_bytes = f.read()
    cache_version = hashlib.sha256(app_js_bytes).hexdigest()[:12]

    with open(f"{dist_dir}/static/app.js", "wb") as f:
        f.write(app_js_bytes)

    # 4. Copy index.html to dist/ with the real bundle version substituted in.
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    html_content = html_content.replace("__CACHE_VERSION__", cache_version)

    with open(f"{dist_dir}/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    # Add .nojekyll for GitHub Pages
    with open(f"{dist_dir}/.nojekyll", "w") as f:
        f.write("")

    print(f"✓ Static export complete! Exported {len(streams_list)} stream summaries to dist/")

if __name__ == "__main__":
    export_static_site()
