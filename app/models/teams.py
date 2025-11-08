"""Pydantic models for Teams payloads (simplified)."""

from pydantic import BaseModel


class TeamsIncomingActivity(BaseModel):
    """Very small subset of a Teams / Bot Framework activity."""

    type: str | None = None
    id: str | None = None
    timestamp: str | None = None
    serviceUrl: str | None = None
    channelId: str | None = None
    conversation_id: str | None = None
    from_id: str | None = None
    text: str | None = None
