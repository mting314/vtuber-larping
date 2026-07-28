import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "vtuber-summaries")
LOCAL_DATA_DIR = Path("data")

# GCS object paths for shared state (DB + yt-dlp cookies). Kept here (in the
# app package) so both the Cloud Run runtime image and CI can use one code path;
# scratch/ is excluded from the Docker image.
DB_BLOB_PATH = os.getenv("DB_BLOB_PATH", "state/vtuber_digest.db")
COOKIES_BLOB_PATH = os.getenv("YT_COOKIES_GCS_BLOB", "state/youtube_cookies.txt")

class StorageManager:
    def __init__(self):
        self.gcs_client = None
        self.bucket = None
        
        # Try initializing GCS client if credentials/project are configured
        try:
            from google.cloud import storage
            self.gcs_client = storage.Client()
            self.bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)
            logger.info(f"GCS Storage initialized for bucket: {GCS_BUCKET_NAME}")
        except Exception as e:
            logger.warning(f"GCS Storage client not initialized ({e}). Falling back to local storage directory.")
            self.gcs_client = None

        # Ensure local fallback directory exists
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        (LOCAL_DATA_DIR / "transcripts").mkdir(exist_ok=True)
        (LOCAL_DATA_DIR / "chunks").mkdir(exist_ok=True)

    def save_transcript(self, video_id: str, content: str) -> str:
        """Saves transcript content to GCS (or local fallback) and returns the URI."""
        filename = f"transcripts/{video_id}.vtt"
        
        if self.bucket:
            try:
                blob = self.bucket.blob(filename)
                blob.upload_from_string(content, content_type="text/vtt")
                gcs_uri = f"gs://{GCS_BUCKET_NAME}/{filename}"
                logger.info(f"Uploaded transcript for {video_id} to {gcs_uri}")
                return gcs_uri
            except Exception as e:
                logger.error(f"GCS upload failed ({e}), using local fallback.")
        
        # Local fallback
        local_path = LOCAL_DATA_DIR / filename
        local_path.write_text(content, encoding="utf-8")
        return str(local_path.absolute())

    def get_transcript(self, video_id: str) -> str | None:
        """Retrieves transcript content from GCS or local storage."""
        filename = f"transcripts/{video_id}.vtt"
        
        if self.bucket:
            try:
                blob = self.bucket.blob(filename)
                if blob.exists():
                    return blob.download_as_text()
            except Exception as e:
                logger.error(f"GCS fetch failed ({e}). Checking local fallback.")
                
        local_path = LOCAL_DATA_DIR / filename
        if local_path.exists():
            return local_path.read_text(encoding="utf-8")

        return None

    # --- Shared-state sync (SQLite DB + yt-dlp cookies) ---
    def download_db(self, local_path: str, blob_name: str = DB_BLOB_PATH) -> bool:
        """Pull the persisted SQLite DB from GCS. Returns True if downloaded."""
        if not self.bucket:
            return False
        try:
            blob = self.bucket.blob(blob_name)
            if blob.exists():
                blob.download_to_filename(local_path)
                logger.info(f"Downloaded DB from gs://{GCS_BUCKET_NAME}/{blob_name}")
                return True
        except Exception as e:
            logger.error(f"DB download failed ({e}).")
        return False

    def upload_db(self, local_path: str, blob_name: str = DB_BLOB_PATH) -> bool:
        """Push the local SQLite DB to GCS. Returns True on success."""
        if not self.bucket or not os.path.exists(local_path):
            return False
        try:
            self.bucket.blob(blob_name).upload_from_filename(local_path)
            logger.info(f"Uploaded DB to gs://{GCS_BUCKET_NAME}/{blob_name}")
            return True
        except Exception as e:
            logger.error(f"DB upload failed ({e}).")
        return False

    def download_cookies(self, local_path: str, blob_name: str = COOKIES_BLOB_PATH) -> bool:
        """Pull yt-dlp cookies.txt from GCS if present. Returns True if downloaded."""
        if not self.bucket:
            return False
        try:
            blob = self.bucket.blob(blob_name)
            if blob.exists():
                blob.download_to_filename(local_path)
                logger.info(f"Downloaded yt-dlp cookies to {local_path}")
                return True
        except Exception as e:
            logger.warning(f"Cookies download failed ({e}).")
        return False

storage_manager = StorageManager()
