import time
import uuid
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, ToolCallLog


class AuditRepository:
    """Writes tool_call_logs and audit_logs - the reconstructable trail behind every agent decision."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_event(
        self,
        event_type: str,
        actor: str,
        conversation_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            event_type=event_type,
            actor=actor,
            conversation_id=conversation_id,
            customer_id=customer_id,
            details=details or {},
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def log_tool_call(
        self,
        conversation_id: uuid.UUID,
        tool_name: str,
        tool_input: dict,
        tool_output: dict | None,
        success: bool,
        duration_ms: int,
        message_id: uuid.UUID | None = None,
        error: str | None = None,
    ) -> ToolCallLog:
        entry = ToolCallLog(
            conversation_id=conversation_id,
            message_id=message_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_tool_calls(self, conversation_id: uuid.UUID) -> list[ToolCallLog]:
        result = await self.session.execute(
            select(ToolCallLog)
            .where(ToolCallLog.conversation_id == conversation_id)
            .order_by(ToolCallLog.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_audit_events(self, conversation_id: uuid.UUID) -> list[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.conversation_id == conversation_id)
            .order_by(AuditLog.created_at.asc())
        )
        return list(result.scalars().all())

    @asynccontextmanager
    async def timed_tool_call(self, conversation_id: uuid.UUID, tool_name: str, tool_input: dict):
        """Usage: async with audit_repo.timed_tool_call(...) as recorder: ... recorder.result = output"""

        class _Recorder:
            result: dict | None = None
            error: str | None = None

        recorder = _Recorder()
        start = time.perf_counter()
        try:
            yield recorder
        except Exception as exc:  # noqa: BLE001 - we log then re-raise
            recorder.error = str(exc)
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await self.log_tool_call(
                conversation_id=conversation_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=recorder.result,
                success=recorder.error is None,
                duration_ms=duration_ms,
                error=recorder.error,
            )
