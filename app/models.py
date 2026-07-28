from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

class JobStatus(str, Enum):
    PENDING = "PENDING"
    FETCHING_TRANSCRIPT = "FETCHING_TRANSCRIPT"
    SUMMARIZING = "SUMMARIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class VTuber(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    channel_id: str = Field(unique=True, index=True)
    agency: str = Field(default="Indies", index=True) # Hololive, Nijisanji, VShojo, Indies
    avatar_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    streams: List["Stream"] = Relationship(back_populates="vtuber")

class Stream(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(unique=True, index=True)
    title: str = Field(index=True)
    duration_seconds: int = Field(default=0)
    published_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    thumbnail_url: Optional[str] = None
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    gcs_transcript_uri: Optional[str] = None
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    
    vtuber_id: Optional[int] = Field(default=None, foreign_key="vtuber.id")
    vtuber: Optional[VTuber] = Relationship(back_populates="streams")

    summary: Optional["Summary"] = Relationship(back_populates="stream")

class Summary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: int = Field(foreign_key="stream.id", unique=True, index=True)
    master_summary: str
    standout_highlights_json: str # JSON array of { timestamp: "MM:SS", text: "..." }
    chunk_data_json: str # JSON array of 15-min chunk summaries
    created_at: datetime = Field(default_factory=datetime.utcnow)

    stream: Optional[Stream] = Relationship(back_populates="summary")

class UserSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    discord_webhook_url: Optional[str] = None
    is_discord_enabled: bool = Field(default=True)
    summary_style: str = Field(default="bullet_first") # bullet_first, detailed, concise
    muted_agencies_json: str = Field(default="[]") # JSON array of muted agency names

