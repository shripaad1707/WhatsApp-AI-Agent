from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.ticket_repo import TicketRepository
from app.schemas.dashboard import ConversationSummary, TicketOut

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_escalated_conversations(session: AsyncSession = Depends(get_session)):
    repo = ConversationRepository(session)
    return await repo.list_escalated()


@router.get("/tickets", response_model=list[TicketOut])
async def list_escalated_tickets(session: AsyncSession = Depends(get_session)):
    repo = TicketRepository(session)
    return await repo.list_escalated()
