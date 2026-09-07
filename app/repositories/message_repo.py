import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, MessageDirection, MessageSender


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(
        self,
        conversation_id: uuid.UUID,
        direction: MessageDirection,
        sender: MessageSender,
        content: str,
        twilio_sid: str | None = None,
        meta: dict | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            direction=direction,
            sender=sender,
            content=content,
            twilio_sid=twilio_sid,
            meta=meta,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def get_recent(self, conversation_id: uuid.UUID, limit: int = 20) -> list[Message]:
        """Last N messages, oldest first (ready to hand to the agent as context)."""
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages
