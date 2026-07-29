# 🗺️ VTuber Digest - Master Project Roadmap & TODO Tracker

This document provides a comprehensive breakdown of all completed milestones, current architectural design decisions, and active TODO tracking for **VTuber Digest (vtuber-larping)**.

---

## 🚀 Active TODOs & Upcoming Roadmap

### 🎮 1. Stream Category Classification (Games vs. Just Chatting)
- [ ] **Title & Transcript-Based Stream Classification:**
  - Classify each ingested stream into **"Gaming"** vs. **"Just Chatting (*Zatsudan*)"** categories.
  - **Title Analysis:** Parse stream title for game tags (e.g., `【Lethal Company】`, `【Minecraft】`, `【Zatsudan】`, `【Chatting】`).
  - **LLM Content Evaluation:** Update Gemini reduce prompt (`MasterSummaryResponse` Pydantic schema in [app/summarizer.py](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/app/summarizer.py#L53)) to evaluate transcript contents and output stream category (`gaming` vs `chatting`).
  - **Data Schema:** Add `stream_category` column to the `Stream` table in [app/models.py](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/app/models.py#L29).
  - **UI Category Tabs:** Add UI filter pills (`All`, `Just Chatting`, `Gaming`) to the GitHub Pages dashboard ([app/static/index.html](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/app/static/index.html)).

### 🗄️ 2. Roadmap B — Hosted Database & Live Backend
- [ ] **Cloud SQL / Firestore Migration:**
  - Replace current SQLite DB (`vtuber_digest.db`) + GCS file-sync design with a managed cloud database.
  - Re-enable live backend on-demand summarization and user settings persistence.

---

## ✅ Completed Milestones

### 📌 Phase 1: Core Ingestion & Map-Reduce Pipeline
- [x] **YouTube VTT Subtitle Extractor ([app/transcriber.py](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/app/transcriber.py)):**
  - Download captions via `yt-dlp` using `--extractor-args "youtube:player_client=android,web"`.
  - Parse `.vtt` cues, strip duplicates/HTML tags, and chunk subtitles into 15-minute logical blocks.
- [x] **Map-Reduce LLM Summarization Engine ([app/summarizer.py](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/app/summarizer.py)):**
  - **Map Phase:** Process 15-minute chunks with Gemini 2.5 Flash on Vertex AI (`TimelineEntry`).
  - **Reduce Phase:** Synthesize master summaries with structured Pydantic schema enforcement.
- [x] **VTuber Name & Formatting Rules:**
  - Enforce explicit VTuber names (`Shiori Novella`, `Gawr Gura`, `FUWAMOCO`, `Ironmouse`, etc.) in prompts and regex fallbacks, banning generic terms like *"the streamer"* or *"the VTuber"*.
  - Bold headline topic titles in chronological timeline breakdown (`- **[HH:MM:SS] Title**: Details`).

### 🍪 Phase 2: Cookies Authentication & Cross-Platform Ingestion
- [x] **yt-dlp Datacenter Bot Protection Bypass ([app/storage.py](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/app/storage.py), [scratch/db_sync.py](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/scratch/db_sync.py)):**
  - Added Netscape `cookies.txt` push (`push-cookies`) and pull (`pull-cookies`) GCS synchronization (`gs://vtuber-summaries/state/youtube_cookies.txt`).
  - Cross-platform temp directory resolution (`tempfile.gettempdir()`) and automated directory creation for cookie downloads on Windows & Linux CI runners.

### 🎨 Phase 3: Web UI Dashboard & Interactive Timestamps
- [x] **Modern Static Dashboard ([app/static/index.html](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/app/static/index.html)):**
  - Glassmorphic dark mode UI with agency filtering pills (`All`, `Hololive`, `NIJISANJI`, `VShojo`, `Indie`).
  - Responsive stream cards with thumbnails, VTuber avatars, publication dates, and duration badges.
- [x] **Interactive Timestamp Seeking:**
  - Transform rendered markdown timestamps (`[HH:MM:SS]`) into interactive links that seek the embedded YouTube iframe (`ytPlayer`) to exact seconds with autoplay.

### 🏛️ Phase 4: Architecture A & Static GitHub Pages Deployment
- [x] **Curated Static Gallery Architecture:**
  - Public site served as read-only static gallery on GitHub Pages (`dist/`).
  - Summaries produced exclusively by batch ingest job ([scratch/ingest_single_stream.py](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/scratch/ingest_single_stream.py)) and GitHub Actions workflows ([.github/workflows/ingest-stream.yml](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/.github/workflows/ingest-stream.yml)).
