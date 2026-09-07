import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    whatsapp_number: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: str
    sender: str
    content: str
    meta: dict | None
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    channel: str
    started_at: datetime
    last_message_at: datetime
    customer: CustomerSummary


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


class ToolCallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool_name: str
    tool_input: dict
    tool_output: dict | None
    success: bool
    error: str | None
    duration_ms: int | None
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    actor: str
    details: dict
    created_at: datetime


class ConversationAuditTrail(BaseModel):
    tool_calls: list[ToolCallLogOut]
    audit_events: list[AuditLogOut]


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    ticket_type: str
    status: str
    priority: str
    description: str | None
    resolution_notes: str | None
    created_at: datetime
    customer: CustomerSummary
