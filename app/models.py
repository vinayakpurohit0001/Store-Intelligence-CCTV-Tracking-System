from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid
from sqlalchemy import Column, String, Boolean, Float, Integer, DateTime, Text
from sqlalchemy.dialects.sqlite import JSON
from app.database import Base

# ── Event type enum ──────────────────────────────────────────────────
class EventType(str, Enum):
    ENTRY                 = "ENTRY"
    EXIT                  = "EXIT"
    ZONE_ENTER            = "ZONE_ENTER"
    ZONE_EXIT             = "ZONE_EXIT"
    ZONE_DWELL            = "ZONE_DWELL"
    BILLING_QUEUE_JOIN    = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY               = "REENTRY"

# ── Pydantic — metadata sub-schema ───────────────────────────────────
class EventMetadata(BaseModel):
    queue_depth: Optional[int]   = None
    sku_zone:    Optional[str]   = None
    session_seq: Optional[int]   = None

# ── Pydantic — inbound event schema ──────────────────────────────────
class EventIn(BaseModel):
    event_id:   str       = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id:   str
    camera_id:  str
    visitor_id: str
    event_type: EventType
    timestamp:  datetime
    zone_id:    Optional[str]   = None
    dwell_ms:   int             = 0
    is_staff:   bool            = False
    confidence: float           = Field(ge=0.0, le=1.0)
    metadata:   EventMetadata   = Field(default_factory=EventMetadata)

    @field_validator('confidence')
    @classmethod
    def confidence_range(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be 0.0 - 1.0")
        return v

# ── Pydantic — ingest request body ───────────────────────────────────
class IngestRequest(BaseModel):
    events: List[EventIn] = Field(max_length=500)

# ── Pydantic — ingest response ───────────────────────────────────────
class IngestResponse(BaseModel):
    accepted:   int
    duplicates: int
    errors:     int
    error_details: List[dict] = []

# ── SQLAlchemy ORM model ─────────────────────────────────────────────
class EventORM(Base):
    __tablename__ = "events"

    event_id   = Column(String,  primary_key=True, index=True)
    store_id   = Column(String,  nullable=False, index=True)
    camera_id  = Column(String,  nullable=False)
    visitor_id = Column(String,  nullable=False, index=True)
    event_type = Column(String,  nullable=False, index=True)
    timestamp  = Column(DateTime, nullable=False, index=True)
    zone_id    = Column(String,  nullable=True)
    dwell_ms   = Column(Integer, default=0)
    is_staff   = Column(Boolean, default=False)
    confidence = Column(Float,   nullable=False)
    meta_queue_depth = Column(Integer, nullable=True)
    meta_sku_zone    = Column(String,  nullable=True)
    meta_session_seq = Column(Integer, nullable=True)
    ingested_at = Column(DateTime, default=datetime.utcnow)
