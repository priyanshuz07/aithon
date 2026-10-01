from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    user_agent: str | None = Field(default=None, max_length=512)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_agent: str | None
    started_at: datetime
    last_seen_at: datetime


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    payload: dict[str, Any] = Field(default_factory=dict)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class HealthRead(BaseModel):
    status: str
    service: str
    database: str
