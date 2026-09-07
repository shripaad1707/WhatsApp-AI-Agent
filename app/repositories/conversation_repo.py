import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Conversation, ConversationStatus


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def get_active_for_customer(self, customer_id: uuid.UUID) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.customer_id == customer_id, Conversation.status == ConversationStatus.ACTIVE)
            .order_by(Conversation.started_at.desc())
        )
        return result.scalars().first()

    async def get_or_create_active(self, customer_id: uuid.UUID) -> Conversation:
        conversation = await self.get_active_for_customer(customer_id)
        if conversation:
            return conversation
        conversation = Conversation(customer_id=customer_id, channel="whatsapp")
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def touch(self, conversation_id: uuid.UUID) -> None:
        conversation = await self.get_by_id(conversation_id)
        if conversation:
            conversation.last_message_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def set_status(self, conversation_id: uuid.UUID, status: ConversationStatus) -> Conversation | None:
        conversation = await self.get_by_id(conversation_id)
        if conversation is None:
            return None
        conversation.status = status
        await self.session.flush()
        return conversation

    async def list_escalated(self) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .options(selectinload(Conversation.customer))
            .where(Conversation.status == ConversationStatus.ESCALATED)
            .order_by(Conversation.last_message_at.desc())
        )
        return list(result.scalars().all())

    async def list_all(self, limit: int = 50) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .options(selectinload(Conversation.customer))
            .order_by(Conversation.last_message_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_with_messages(self, conversation_id) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation)
            .options(selectinload(Conversation.customer), selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()
