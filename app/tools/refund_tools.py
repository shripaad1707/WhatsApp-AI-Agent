from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.repositories.order_repo import OrderRepository
from app.tools.context import ToolContext, tool_result
from app.tools.refund_policy import check_refund_eligibility


class CheckRefundEligibilityInput(BaseModel):
    order_number: str = Field(description="The order number to check refund eligibility for, e.g. 'ORD-100004'.")


def build_refund_tools(ctx: ToolContext) -> list:
    @tool(args_schema=CheckRefundEligibilityInput, response_format="content_and_artifact")
    async def check_refund_eligibility_tool(order_number: str) -> tuple[str, dict]:
        """Check whether an order is eligible for a refund. This runs the company's
        actual refund policy (return window + order status) against the order's real
        data - it does not guess. Always call this before telling a customer whether
        their refund is approved; never state an eligibility judgment on your own."""
        async with ctx.audit_repo.timed_tool_call(
            ctx.conversation_id, "check_refund_eligibility", {"order_number": order_number}
        ) as rec:
            order_repo = OrderRepository(ctx.session)
            order = await order_repo.get_by_order_number(order_number.strip())
            if order is None or order.customer_id != ctx.customer_id:
                rec.result = {"found": False, "reason": "No order with that number for this customer."}
                return tool_result(rec.result)

            result = check_refund_eligibility(order.status, order.delivered_at)
            rec.result = {
                "found": True,
                "order_number": order.order_number,
                "order_total": float(order.total_amount),
                "eligibility": result.eligibility.value,
                "reason": result.reason,
                "days_since_delivery": result.days_since_delivery,
            }
            return tool_result(rec.result)

    return [check_refund_eligibility_tool]
