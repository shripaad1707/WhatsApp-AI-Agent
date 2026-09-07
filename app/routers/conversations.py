import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.repositories.audit_repo import AuditRepository
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.dashboard import ConversationAuditTrail, ConversationDetail, ConversationSummary

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(limit: int = 50, session: AsyncSession = Depends(get_session)):
    repo = ConversationRepository(session)
    conversations = await repo.list_all(limit=limit)
    return conversations


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = ConversationRepository(session)
    conversation = await repo.get_with_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/{conversation_id}/audit", response_model=ConversationAuditTrail)
async def get_conversation_audit_trail(conversation_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    audit_repo = AuditRepository(session)
    tool_calls = await audit_repo.list_tool_calls(conversation_id)
    audit_events = await audit_repo.list_audit_events(conversation_id)
    return ConversationAuditTrail(tool_calls=tool_calls, audit_events=audit_events)
