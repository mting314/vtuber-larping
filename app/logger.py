import logging
import sys
from pathlib import Path

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Log Formatter
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """Utility to set up a dedicated logger with both file and console handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if re-initialized
    if not logger.handlers:
        # File Handler
        fh = logging.FileHandler(LOGS_DIR / log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        # Console Handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger

# Dedicated Phase 2 Loggers
ingestion_logger = setup_logger("vtuber_digest.ingestion", "ingestion.log")
manual_logger = setup_logger("vtuber_digest.manual", "manual_ingestion.log")
pipeline_logger = setup_logger("vtuber_digest.pipeline", "summarization_pipeline.log")
discord_logger = setup_logger("vtuber_digest.discord", "discord_dispatcher.log")
