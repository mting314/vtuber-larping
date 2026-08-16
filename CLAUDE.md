# CLAUDE.md — VTuber Digest (vtuber-larping)

Context for Claude Code working in this repo.

> Full architecture writeup: [`docs/design.md`](docs/design.md) — ingest paths, the
> map-reduce pipeline, the GCS compare-and-swap persistence model, and current known breaks.

## What this is

An automated **Map-Reduce LLM summarization pipeline** for VTuber "just chatting"
(*zatsudan*) streams. It ingests YouTube auto-caption transcripts, chunks them into
15-minute segments, summarizes each with **Gemini 2.5 Flash on Vertex AI** (map),
synthesizes a master summary with exact `[HH:MM:SS]` timestamps (reduce), stores
results in SQLite, and dispatches Discord webhook embeds.

## Architecture (current = "A", read-only gallery)

The app is a **curated static gallery**. Summaries are created only by the **batch ingest
job** (`scratch/ingest_single_stream.py`, run via the `ingest-stream` GitHub Action), which
writes to a SQLite DB persisted in **GCS** (`gs://vtuber-summaries/state/vtuber_digest.db`)
and exports static JSON to **GitHub Pages**. The public site is **read-only**: on the static
host the live "Summarize Stream" / "Settings" actions are hidden (`app.js` hides
`#headerActions` when `isStaticHost`).

- **FastAPI backend** (`app/main.py`) — the local dev server (`uvicorn`), the code the batch
  ingest imports, and the **WebSub push receiver** on Cloud Run. `deploy-cloudrun.yml` is
  manual-dispatch only, but the service is live and YouTube pushes to
  `/api/webhooks/youtube` on every tracked-channel feed update.
- **Runtime GCS persistence** (`app/persistence.py`) — the container's SQLite file is
  ephemeral (scale-to-zero wipes it), so the backend pulls the DB from GCS on startup and
  writes each finished stream back via `persist_stream_to_gcs()`. That write is a
  **compare-and-swap**, not a file overwrite: it merges the one stream into a fresh copy of
  the remote DB and uploads with `if_generation_match`, retrying on 412. Never add a plain
  `upload_db()` call to the runtime path — with `maxScale: 20` it silently drops whatever
  another instance wrote. Rows are keyed on `Stream.video_id` / `VTuber.channel_id`; the
  autoincrement `id`s differ per database and must not be copied across.
- **Static GitHub Pages site** — read-only export (`dist/`) built by
  `scratch/export_static_gh_pages.py`; serves `index.html` + pre-baked JSON
  (`api/streams.json`, `api/streams/<id>.json`). Cannot serve POST.

## Roadmap & Tracked TODOs

- **Games vs. Chatting Stream Separation:** Separate streams into "Gaming" vs. "Just Chatting (*Zatsudan*)" categories. Classification should combine YouTube title analysis (e.g. game title brackets `【Lethal Company】`, `【Minecraft】`) with LLM categorization of the summarized transcript content.
- **Roadmap B:** Replace SQLite + GCS-sync with a real hosted DB (Cloud SQL/Firestore) and re-enable a live backend + on-demand summarization.

The single `app/static/index.html` runs in both places and switches behavior at runtime
based on `window.location.hostname` (see "Frontend backend routing" below).

## Layout

```
app/
  main.py          FastAPI app: routes + process_stream_pipeline() background task + startup seed
  models.py        SQLModel tables: VTuber, Stream, Summary, UserSettings, JobStatus enum
  database.py      SQLite engine (DATABASE_FILE env, default vtuber_digest.db), init_db()
  transcriber.py   yt-dlp VTT download, parse_vtt(), chunk_cues(interval_minutes=15)
  summarizer.py    run_map_reduce_pipeline() — Gemini map + reduce, Pydantic-enforced JSON
  glossary.py      VTuber name normalizer (fixes caption typos: Crony->Kronii, etc.)
  discord.py       send_discord_summary_embed() webhook dispatcher
  ingestion.py     parse_youtube_atom_feed() (WebSub), poll_channel_rss() (fallback)
  storage.py       StorageManager — GCS with local data/ fallback; generation-checked DB I/O
  persistence.py   compare-and-swap write-back of pipeline results to the GCS DB
  logger.py        named loggers (ingestion/manual/pipeline)
  static/index.html  entire frontend (inline JS+CSS, ~915 lines)
scratch/           one-off ops scripts (ingest, batch, export, migrate, reseed) — NOT app code
.github/workflows/ ci.yml, deploy-pages.yml, ingest-stream.yml
Dockerfile         Cloud Run image
tests/             pytest (test_ingestion, test_transcriber)
```

## Frontend backend routing (critical)

The frontend JS lives in **`app/static/app.js`** (extracted from `index.html`) and is loaded
as `./static/app.js?v=<sha256>` — a real content-hash cache buster injected by both
`read_root()` (backend) and the exporter (Pages). `index.html` carries the `__CACHE_VERSION__`
placeholder that gets substituted at serve/export time.

- `isStaticHost` (github.io / file:) — GET reads point at `./api/*.json`, and the live
  actions (`#headerActions`: Summarize/Settings) are **hidden** (read-only gallery).
- `getActiveBackendUrl()` / `PROD_BACKEND_URL` — only relevant for the (now-hidden) POST
  actions and for local dev. POSTing to the static origin returns **405** (static host allows
  only GET/HEAD) — the historical Summarize-flow 405 came from stale cached inline JS falling
  back to a same-origin POST; the content-hash bundle + hidden actions fix that.

## Deploy model (know before touching deploys)

- **GitHub Pages** (single source = "GitHub Actions" artifact flow):
  - `deploy-pages.yml`: on push to `main` / manual — pulls the DB from GCS
    (`scratch/db_sync.py pull`), exports `dist/`, deploys via `actions/deploy-pages@v4`.
  - `ingest-stream.yml`: manual dispatch — pulls DB, ingests one stream, pushes DB back to
    GCS, re-exports, deploys via the same artifact flow. (The old `gh-pages` branch was
    deleted; do not reintroduce a branch-based Pages source.)
- **GCS is the source of truth** for summary data: `gs://vtuber-summaries/state/vtuber_digest.db`.
  Both Pages workflows need the `GCP_VERTEX_SA_KEY` secret (a JSON key for the compute SA
  `467039506910-compute@…`); the GCS steps skip gracefully if it's unset.
- **Cloud Run** (`deploy-cloudrun.yml`) is **manual-dispatch only** and retired from the data
  path under Architecture A. The `Dockerfile` no longer copies the DB (the app inits its own).
- Auth in CI uses `google-github-actions/auth` (ADC) — the summarizer's `vertexai=True` needs
  ADC, so a bare env var is not enough.

## Common commands

```bash
uv sync                                                    # install deps
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000   # local dev server
uv run python -m scratch.export_static_gh_pages           # build dist/ for Pages
uv run python -m scratch.ingest_single_stream --url <url> # ingest one stream into the DB
uv run ruff check app/ tests/                             # lint (matches CI)
uv run pytest tests/                                       # tests (matches CI)
```

## Conventions / gotchas

- Python 3.12+, `uv` for deps, FastAPI + SQLModel + SQLite, Gemini via `google-genai`.
- Ruff line-length 120; several rules ignored (see `pyproject.toml`).
- `datetime.utcnow()` used throughout (DTZ003 intentionally ignored).
- Summaries store JSON as strings in SQLite columns (`*_json`) — parse with `json.loads`.
- Timestamps in summaries are `[HH:MM:SS]` / `[MM:SS]`; the frontend rewrites them into
  clickable YouTube-seek links.
- `scratch/` = throwaway operational scripts, not importable app surface (though they import
  from `app.*`). Don't build product features there.
