from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.db.models import Ticket, TicketPriority, TicketType
from app.repositories.order_repo import OrderRepository
from app.repositories.ticket_repo import TicketRepository
from app.tools.context import ToolContext, tool_result


def _serialize_ticket(ticket: Ticket) -> dict:
    return {
        "id": str(ticket.id),
        "subject": ticket.subject,
        "ticket_type": ticket.ticket_type.value,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
    }


class CreateTicketInput(BaseModel):
    subject: str = Field(description="Short summary of the issue, e.g. 'Refund request for ORD-100004'.")
    ticket_type: TicketType = Field(description="One of: general, refund_request, complaint, order_issue.")
    description: str | None = Field(default=None, description="Fuller detail on the customer's issue.")
    order_number: str | None = Field(default=None, description="Related order number, if any.")


def build_ticket_tools(ctx: ToolContext) -> list:
    @tool(args_schema=CreateTicketInput, response_format="content_and_artifact")
    async def create_ticket(
        subject: str,
        ticket_type: TicketType,
        description: str | None = None,
        order_number: str | None = None,
    ) -> tuple[str, dict]:
        """Create a support ticket for the identified customer - e.g. to record a refund
        request or a complaint that needs follow-up. Note: this only records the ticket;
        it does NOT by itself decide whether the conversation is handed off to a human -
        that decision is made separately after you respond."""
        async with ctx.audit_repo.timed_tool_call(
            ctx.conversation_id,
            "create_ticket",
            {"subject": subject, "ticket_type": str(ticket_type), "order_number": order_number},
        ) as rec:
            order_id = None
            if order_number:
                order_repo = OrderRepository(ctx.session)
                order = await order_repo.get_by_order_number(order_number.strip())
                if order is not None and order.customer_id == ctx.customer_id:
                    order_id = order.id

            ticket_repo = TicketRepository(ctx.session)
            ticket = await ticket_repo.create(
                customer_id=ctx.customer_id,
                subject=subject,
                ticket_type=ticket_type,
                order_id=order_id,
                conversation_id=ctx.conversation_id,
                description=description,
                priority=TicketPriority.NORMAL,
            )
            rec.result = {"created": True, "ticket": _serialize_ticket(ticket)}
            return tool_result(rec.result)

    @tool(response_format="content_and_artifact")
    async def list_my_tickets() -> tuple[str, dict]:
        """List existing support tickets for the identified customer."""
        async with ctx.audit_repo.timed_tool_call(ctx.conversation_id, "list_my_tickets", {}) as rec:
            ticket_repo = TicketRepository(ctx.session)
            tickets = await ticket_repo.list_for_customer(ctx.customer_id)
            rec.result = {"tickets": [_serialize_ticket(t) for t in tickets]}
            return tool_result(rec.result)

    return [create_ticket, list_my_tickets]
