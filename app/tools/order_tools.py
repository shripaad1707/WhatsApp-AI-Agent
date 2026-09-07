from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.db.models import Order
from app.repositories.order_repo import OrderRepository
from app.tools.context import ToolContext, tool_result


def _serialize_order(order: Order) -> dict:
    return {
        "order_number": order.order_number,
        "status": order.status.value,
        "total_amount": float(order.total_amount),
        "currency": order.currency,
        "tracking_number": order.tracking_number,
        "order_date": order.order_date.isoformat() if order.order_date else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "items": [
            {
                "product_name": item.product.name,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
            }
            for item in order.items
        ],
    }


class LookupOrderInput(BaseModel):
    order_number: str | None = Field(
        default=None,
        description="The order number to look up, e.g. 'ORD-100004'. Omit to get the customer's most recent order.",
    )


def build_order_tools(ctx: ToolContext) -> list:
    @tool(args_schema=LookupOrderInput, response_format="content_and_artifact")
    async def lookup_order(order_number: str | None = None) -> tuple[str, dict]:
        """Look up an order's status, tracking info, and line items for the identified
        customer. Pass order_number if the customer mentioned one; otherwise omit it to
        get their most recent order. Only ever returns orders belonging to this customer -
        an order number for someone else's order will come back as not found."""
        async with ctx.audit_repo.timed_tool_call(
            ctx.conversation_id, "lookup_order", {"order_number": order_number}
        ) as rec:
            repo = OrderRepository(ctx.session)
            if order_number:
                order = await repo.get_by_order_number(order_number.strip())
                if order is None or order.customer_id != ctx.customer_id:
                    rec.result = {"found": False, "reason": "No order with that number for this customer."}
                    return tool_result(rec.result)
            else:
                order = await repo.get_latest_for_customer(ctx.customer_id)
                if order is None:
                    rec.result = {"found": False, "reason": "This customer has no orders."}
                    return tool_result(rec.result)

            rec.result = {"found": True, "order": _serialize_order(order)}
            return tool_result(rec.result)

    @tool(response_format="content_and_artifact")
    async def list_my_orders() -> tuple[str, dict]:
        """List all orders for the identified customer, most recent first. Use this when
        the customer asks about multiple orders or doesn't specify which one."""
        async with ctx.audit_repo.timed_tool_call(ctx.conversation_id, "list_my_orders", {}) as rec:
            repo = OrderRepository(ctx.session)
            orders = await repo.list_for_customer(ctx.customer_id)
            rec.result = {"orders": [_serialize_order(o) for o in orders]}
            return tool_result(rec.result)

    return [lookup_order, list_my_orders]
