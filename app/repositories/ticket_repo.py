import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Ticket, TicketPriority, TicketStatus, TicketType


class TicketRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        return await self.session.get(Ticket, ticket_id)

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[Ticket]:
        result = await self.session.execute(
            select(Ticket).where(Ticket.customer_id == customer_id).order_by(Ticket.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_escalated(self) -> list[Ticket]:
        result = await self.session.execute(
            select(Ticket)
            .options(selectinload(Ticket.customer))
            .where(Ticket.status == TicketStatus.ESCALATED)
            .order_by(Ticket.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all(self, status: TicketStatus | None = None, limit: int = 100) -> list[Ticket]:
        stmt = select(Ticket).options(selectinload(Ticket.customer)).order_by(Ticket.created_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(Ticket.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        customer_id: uuid.UUID,
        subject: str,
        ticket_type: TicketType,
        order_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        description: str | None = None,
        priority: TicketPriority = TicketPriority.NORMAL,
        status: TicketStatus = TicketStatus.OPEN,
    ) -> Ticket:
        ticket = Ticket(
            customer_id=customer_id,
            order_id=order_id,
            conversation_id=conversation_id,
            subject=subject,
            ticket_type=ticket_type,
            description=description,
            priority=priority,
            status=status,
        )
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def update_status(
        self, ticket_id: uuid.UUID, status: TicketStatus, resolution_notes: str | None = None
    ) -> Ticket | None:
        ticket = await self.get_by_id(ticket_id)
        if ticket is None:
            return None
        ticket.status = status
        if resolution_notes is not None:
            ticket.resolution_notes = resolution_notes
        await self.session.flush()
        return ticket
