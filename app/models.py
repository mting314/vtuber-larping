from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class JobStatus(str, Enum):
    PENDING = "PENDING"
    FETCHING_TRANSCRIPT = "FETCHING_TRANSCRIPT"
    SUMMARIZING = "SUMMARIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class VTuber(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    channel_id: str = Field(unique=True, index=True)
    agency: str = Field(default="Indies", index=True) # Hololive, Nijisanji, VShojo, Indies
    avatar_url: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    streams: list["Stream"] = Relationship(back_populates="vtuber")

class Stream(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    video_id: str = Field(unique=True, index=True)
    title: str = Field(index=True)
    stream_category: str = Field(default="chatting", index=True)  # "chatting" vs "gaming"
    duration_seconds: int = Field(default=0)
    published_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    thumbnail_url: str | None = None
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    gcs_transcript_uri: str | None = None
    error_message: str | None = None
    warning_message: str | None = None

    # Bounded-retry bookkeeping. A FAILED row is re-attempted on an exponential
    # backoff until retry_count hits the cap, then left alone until a human
    # re-triggers it. Without this, transient failures (bot checks, 429s) either
    # never recover or get retried on every cold start — the latter is what got
    # the Cloud Run egress IP flagged by YouTube.
    retry_count: int = Field(default=0)
    last_attempted_at: datetime | None = None
    
    vtuber_id: int | None = Field(default=None, foreign_key="vtuber.id")
    vtuber: VTuber | None = Relationship(back_populates="streams")

    summary: Optional["Summary"] = Relationship(back_populates="stream")

class Summary(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    stream_id: int = Field(foreign_key="stream.id", unique=True, index=True)
    master_summary: str
    standout_highlights_json: str # JSON array of { timestamp: "MM:SS", text: "..." }
    chunk_data_json: str # JSON array of 15-min chunk summaries
    created_at: datetime = Field(default_factory=datetime.utcnow)

    stream: Stream | None = Relationship(back_populates="summary")

class UserSettings(SQLModel, table=True):
    id: int | None = Field(default=1, primary_key=True)
    discord_webhook_url: str | None = None
    is_discord_enabled: bool = Field(default=True)
    summary_style: str = Field(default="bullet_first") # bullet_first, detailed, concise
    muted_agencies_json: str = Field(default="[]") # JSON array of muted agency names

