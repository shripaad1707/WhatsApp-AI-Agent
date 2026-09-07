"""The end-to-end message pipeline:

WhatsApp -> Customer Identification -> Conversation Memory -> RAG -> AI Agent -> Tools
-> Decision Engine -> Auto-Reply OR Human Handoff.

Everything except the "AI Agent" call is plain, deterministic Python - the LLM never
decides whether to escalate, it only decides what to say and which tools to call.
"""

import asyncio

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import run_agent
from app.agent.memory import messages_to_langchain
from app.agent.prompts import build_system_prompt
from app.config import Settings
from app.db.models import ConversationStatus, MessageDirection, MessageSender, TicketPriority, TicketStatus, TicketType
from app.decision_engine.engine import DecisionEngine
from app.decision_engine.rules import wants_human
from app.repositories.audit_repo import AuditRepository
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.customer_repo import CustomerRepository
from app.repositories.kb_repo import KBRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.ticket_repo import TicketRepository
from app.schemas.whatsapp import InboundWhatsAppMessage
from app.services.embeddings import EmbeddingService
from app.services.rag import retrieve_policy_context
from app.services.whatsapp import WhatsAppService
from app.tools.context import ToolContext
from app.tools.refund_policy import RefundEligibility
from app.tools.registry import build_all_tools

logger = structlog.get_logger(__name__)

SHORT_TERM_MEMORY_SIZE = 20

HANDOFF_ACK_MESSAGE = (
    "Thanks for the details - I'm connecting you with a member of our support team "
    "who will follow up with you here shortly."
)


def _extract_order_value(tool_artifacts: dict) -> float | None:
    refund_artifact = tool_artifacts.get("check_refund_eligibility_tool")
    if refund_artifact and refund_artifact.get("found"):
        return float(refund_artifact["order_total"])

    order_artifact = tool_artifacts.get("lookup_order")
    if order_artifact and order_artifact.get("found"):
        return float(order_artifact["order"]["total_amount"])

    return None


def _extract_refund_eligibility(tool_artifacts: dict) -> RefundEligibility | None:
    refund_artifact = tool_artifacts.get("check_refund_eligibility_tool")
    if refund_artifact and refund_artifact.get("found"):
        return RefundEligibility(refund_artifact["eligibility"])
    return None


def _extract_refund_order_number(tool_artifacts: dict) -> str | None:
    refund_artifact = tool_artifacts.get("check_refund_eligibility_tool")
    if refund_artifact and refund_artifact.get("found"):
        return refund_artifact["order_number"]
    return None


async def handle_inbound_message(
    session: AsyncSession,
    inbound: InboundWhatsAppMessage,
    whatsapp: WhatsAppService,
    embedder: EmbeddingService,
    chat_model: BaseChatModel,
    settings: Settings,
) -> dict:
    """Processes one inbound WhatsApp message end-to-end. Returns a summary dict (used
    by tests and the demo scripts) describing what happened."""

    customer_repo = CustomerRepository(session)
    conversation_repo = ConversationRepository(session)
    message_repo = MessageRepository(session)
    audit_repo = AuditRepository(session)
    ticket_repo = TicketRepository(session)
    order_repo = OrderRepository(session)
    kb_repo = KBRepository(session)

    # --- Deterministic: Customer Identification ---
    customer = await customer_repo.get_or_create(inbound.from_number, name=inbound.profile_name)
    conversation = await conversation_repo.get_or_create_active(customer.id)

    await audit_repo.log_event(
        "message_received",
        actor="system",
        conversation_id=conversation.id,
        customer_id=customer.id,
        details={"body": inbound.body, "twilio_sid": inbound.message_sid},
    )

    inbound_msg = await message_repo.add(
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        sender=MessageSender.CUSTOMER,
        content=inbound.body,
        twilio_sid=inbound.message_sid,
    )

    # --- Deterministic: explicit "talk to a human" bypasses the agent entirely ---
    engine = DecisionEngine(settings.confidence_threshold, settings.high_value_threshold)

    if wants_human(inbound.body):
        return await _escalate(
            session=session,
            conversation_id=conversation.id,
            customer_id=customer.id,
            ticket_repo=ticket_repo,
            conversation_repo=conversation_repo,
            message_repo=message_repo,
            audit_repo=audit_repo,
            whatsapp=whatsapp,
            to_number=inbound.from_number,
            reason="Customer explicitly asked to speak with a human.",
            ticket_subject=f"Human requested: {inbound.body[:80]}",
            ticket_type=TicketType.GENERAL,
            agent_output=None,
        )

    # --- Conversation Memory: short-term (last N messages), long-term (customer fields) ---
    recent_messages = await message_repo.get_recent(conversation.id, limit=SHORT_TERM_MEMORY_SIZE)
    history = messages_to_langchain(recent_messages[:-1])  # exclude the message we just added

    # --- RAG: retrieve policy grounding for this message ---
    policy_context = await retrieve_policy_context(kb_repo, embedder, inbound.body)
    system_prompt = build_system_prompt(customer.name, policy_context)

    # --- AI Agent: ReAct tool-calling loop within a closed, customer-scoped tool set ---
    tool_ctx = ToolContext(
        session=session, customer_id=customer.id, conversation_id=conversation.id, audit_repo=audit_repo
    )
    tools = build_all_tools(tool_ctx)
    agent_output, tool_artifacts = await run_agent(
        model=chat_model, tools=tools, system_prompt=system_prompt, history=history, customer_message=inbound.body
    )

    await audit_repo.log_event(
        "agent_completed",
        actor="ai",
        conversation_id=conversation.id,
        customer_id=customer.id,
        details={
            "intent": agent_output.intent.value,
            "confidence": agent_output.confidence,
            "tools_called": agent_output.tools_called,
            "recommend_handoff": agent_output.recommend_handoff,
        },
    )

    # --- Decision Engine: deterministic auto-reply-vs-handoff call, never the LLM's ---
    order_value = _extract_order_value(tool_artifacts)
    refund_eligibility = _extract_refund_eligibility(tool_artifacts)
    decision = engine.evaluate(inbound.body, agent_output, order_value=order_value, refund_eligibility=refund_eligibility)

    await audit_repo.log_event(
        "decision_engine_evaluated",
        actor="system",
        conversation_id=conversation.id,
        customer_id=customer.id,
        details={
            "should_handoff": decision.should_handoff,
            "reason": decision.reason,
            "auto_process_refund": decision.auto_process_refund,
            "order_value": order_value,
            "refund_eligibility": refund_eligibility.value if refund_eligibility else None,
        },
    )

    if decision.should_handoff:
        return await _escalate(
            session=session,
            conversation_id=conversation.id,
            customer_id=customer.id,
            ticket_repo=ticket_repo,
            conversation_repo=conversation_repo,
            message_repo=message_repo,
            audit_repo=audit_repo,
            whatsapp=whatsapp,
            to_number=inbound.from_number,
            reason=decision.reason or "Escalated by Decision Engine.",
            ticket_subject=f"Escalation: {agent_output.intent.value} - {inbound.body[:60]}",
            ticket_type=TicketType.REFUND_REQUEST if agent_output.intent.value == "refund_request" else TicketType.GENERAL,
            agent_output=agent_output,
        )

    # --- Auto-approved refund: deterministic status change, not an agent tool ---
    if decision.auto_process_refund:
        order_number = _extract_refund_order_number(tool_artifacts)
        if order_number:
            order = await order_repo.get_by_order_number(order_number)
            if order is not None:
                await order_repo.mark_refunded(order.id)
                await audit_repo.log_event(
                    "refund_auto_processed",
                    actor="system",
                    conversation_id=conversation.id,
                    customer_id=customer.id,
                    details={"order_number": order_number, "order_value": order_value},
                )

    # --- Send the agent's (validated, structured) reply ---
    sid = await asyncio.to_thread(whatsapp.send_message, inbound.from_number, agent_output.reply_text)
    await message_repo.add(
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.AI_AGENT,
        content=agent_output.reply_text,
        twilio_sid=sid,
        meta=agent_output.model_dump(mode="json"),
    )
    await conversation_repo.touch(conversation.id)
    await session.commit()

    return {
        "handoff": False,
        "reply_text": agent_output.reply_text,
        "intent": agent_output.intent.value,
        "confidence": agent_output.confidence,
        "auto_process_refund": decision.auto_process_refund,
    }


async def _escalate(
    session: AsyncSession,
    conversation_id,
    customer_id,
    ticket_repo: TicketRepository,
    conversation_repo: ConversationRepository,
    message_repo: MessageRepository,
    audit_repo: AuditRepository,
    whatsapp: WhatsAppService,
    to_number: str,
    reason: str,
    ticket_subject: str,
    ticket_type: TicketType,
    agent_output,
) -> dict:
    ticket = await ticket_repo.create(
        customer_id=customer_id,
        subject=ticket_subject,
        ticket_type=ticket_type,
        conversation_id=conversation_id,
        description=reason,
        priority=TicketPriority.HIGH,
        status=TicketStatus.ESCALATED,
    )
    await conversation_repo.set_status(conversation_id, ConversationStatus.ESCALATED)

    await audit_repo.log_event(
        "handoff_triggered",
        actor="system",
        conversation_id=conversation_id,
        customer_id=customer_id,
        details={
            "reason": reason,
            "ticket_id": str(ticket.id),
            "agent_draft": agent_output.reply_text if agent_output else None,
        },
    )

    sid = await asyncio.to_thread(whatsapp.send_message, to_number, HANDOFF_ACK_MESSAGE)
    await message_repo.add(
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.SYSTEM,
        content=HANDOFF_ACK_MESSAGE,
        twilio_sid=sid,
    )
    await conversation_repo.touch(conversation_id)
    await session.commit()

    return {"handoff": True, "reason": reason, "ticket_id": str(ticket.id)}
