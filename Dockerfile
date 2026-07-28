FROM python:3.13-slim

# Install system dependencies (ffmpeg, curl, git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp binary
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

# Set working directory
WORKDIR /app

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv
ENV PATH="/uv/bin:$PATH"

# Copy pyproject.toml, uv.lock, and README.md
COPY pyproject.toml uv.lock README.md ./

# Install project dependencies into virtual environment /app/.venv
RUN uv sync --frozen --no-cache

# Copy application source code.
# NOTE: the SQLite DB is intentionally NOT copied — it is gitignored/untracked,
# so `COPY vtuber_digest.db` broke the build in CI. The app calls init_db() on
# startup and seeds default VTubers, so the container boots with a fresh DB.
# Curated summary data is persisted separately in GCS (see scratch/db_sync.py).
COPY app/ ./app/

# Expose port 8080 for Cloud Run
ENV PORT=8080
EXPOSE 8080

# Execute uvicorn directly from the virtual environment for instant sub-second boot time
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
