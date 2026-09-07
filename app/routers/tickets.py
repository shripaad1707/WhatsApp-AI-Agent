import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models import TicketStatus
from app.repositories.ticket_repo import TicketRepository
from app.schemas.dashboard import TicketOut

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
async def list_tickets(status: TicketStatus | None = None, session: AsyncSession = Depends(get_session)):
    repo = TicketRepository(session)
    return await repo.list_all(status=status)


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = TicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    # Ensure customer is loaded for the response model.
    await session.refresh(ticket, attribute_names=["customer"])
    return ticket
