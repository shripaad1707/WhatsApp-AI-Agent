"""Per-conversation context that tools are closed over - never something the LLM supplies.

Customer identification happens deterministically in the message pipeline BEFORE the
agent ever runs. Binding customer_id here (rather than accepting it as a tool argument)
means the LLM cannot ask a tool to fetch another customer's data even if it tried.
"""

import json
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_repo import AuditRepository


@dataclass
class ToolContext:
    session: AsyncSession
    customer_id: uuid.UUID
    conversation_id: uuid.UUID
    audit_repo: AuditRepository


def tool_result(data: dict) -> tuple[str, dict]:
    """Pairs the LLM-visible text (clean JSON) with the raw dict artifact the pipeline
    reads back after the agent run (e.g. to apply the refund-eligibility decision).
    Used with @tool(..., response_format="content_and_artifact")."""
    return json.dumps(data, default=str), data
