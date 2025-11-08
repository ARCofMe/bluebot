"""Pydantic models representing BlueFolder-related data the bot might use."""

from pydantic import BaseModel


class AssignmentSummary(BaseModel):
    assignment_id: str
    service_request_id: str
    subject: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    start: str | None = None
    end: str | None = None
    is_complete: bool | None = None
