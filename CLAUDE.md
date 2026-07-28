# CLAUDE.md — VTuber Digest (vtuber-larping)

Context for Claude Code working in this repo.

## What this is

An automated **Map-Reduce LLM summarization pipeline** for VTuber "just chatting"
(*zatsudan*) streams. It ingests YouTube auto-caption transcripts, chunks them into
15-minute segments, summarizes each with **Gemini 2.5 Flash on Vertex AI** (map),
synthesizes a master summary with exact `[HH:MM:SS]` timestamps (reduce), stores
results in SQLite, and dispatches Discord webhook embeds.

There are **two independent runtime surfaces** — this is the source of most deploy confusion:

1. **FastAPI backend** (`app/main.py`) — the full dynamic app (POST triggers, background
   pipeline, settings). Runs locally (`uvicorn`) and is deployed to **Google Cloud Run**.
2. **Static GitHub Pages site** — a read-only export (`dist/`) built by
   `scratch/export_static_gh_pages.py`. It serves the same `index.html` but only pre-baked
   JSON (`api/streams.json`, `api/streams/<id>.json`). It **cannot** serve POST requests.

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
  storage.py       StorageManager — GCS with local data/ fallback
  logger.py        named loggers (ingestion/manual/pipeline)
  static/index.html  entire frontend (inline JS+CSS, ~915 lines)
scratch/           one-off ops scripts (ingest, batch, export, migrate, reseed) — NOT app code
.github/workflows/ ci.yml, deploy-pages.yml, ingest-stream.yml
Dockerfile         Cloud Run image
tests/             pytest (test_ingestion, test_transcriber)
```

## Frontend backend routing (critical)

In `app/static/index.html`:
- `PROD_BACKEND_URL` — hardcoded Cloud Run URL, currently
  `https://vtuber-digest-backend-467039506910.us-central1.run.app`.
- `getActiveBackendUrl()` — returns `PROD_BACKEND_URL` on any non-localhost host;
  only on `localhost`/`127.0.0.1` does it read `localStorage['backend_api_url']`
  (dev override, default `http://127.0.0.1:8000`).
- `isStaticHost` (github.io / file:) — makes GET reads point at `./api/*.json` instead of
  the live API. **POST actions (Summarize Stream, Settings save) always target
  `getActiveBackendUrl()`**, i.e. Cloud Run.

**If you POST to the GitHub Pages origin itself you get HTTP 405** (static host allows only
GET/HEAD). Historically the URL-resolution logic fell back to a same-origin relative path,
which is what produced the 405 on the Summarize flow. The JS is inline in `index.html`, so a
stale browser cache of an old `index.html` reintroduces the old bug for returning users. The
`?v=<timestamp>` "cache buster" injected by the exporter only prints to `console.log` — it
does **not** actually bust the HTML cache.

## Deploy model (know before touching deploys)

- **Cloud Run backend has NO CI workflow** — it is deployed manually (`gcloud run deploy` /
  `gcloud builds submit` from a dev machine). The `Dockerfile` does
  `COPY vtuber_digest.db ./vtuber_digest.db`, but the `.db` is **gitignored and untracked**,
  so the image only builds where that file exists locally. CI cannot build it.
- **GitHub Pages has TWO competing deploy paths** — reconcile before editing:
  - `deploy-pages.yml`: on push to `main`, exports `dist/` and deploys via the modern
    `actions/deploy-pages@v4` artifact flow.
  - `ingest-stream.yml`: on manual dispatch, force-pushes `dist/` to a `gh-pages` branch.
  GitHub Pages can only have one source; whichever the repo Settings points at wins, and the
  other silently does nothing.
- The site DB is ephemeral: exports call `init_db()` and read whatever `vtuber_digest.db` is
  present in the runner. Real summaries are seeded/ingested via `scratch/` scripts.

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
