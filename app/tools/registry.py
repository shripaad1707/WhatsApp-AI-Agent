from app.tools.context import ToolContext
from app.tools.customer_tools import build_customer_tools
from app.tools.order_tools import build_order_tools
from app.tools.product_tools import build_product_tools
from app.tools.refund_tools import build_refund_tools
from app.tools.ticket_tools import build_ticket_tools


def build_all_tools(ctx: ToolContext) -> list:
    """The agent's closed tool set - nothing outside this list is reachable."""
    return [
        *build_customer_tools(ctx),
        *build_order_tools(ctx),
        *build_product_tools(ctx),
        *build_ticket_tools(ctx),
        *build_refund_tools(ctx),
    ]
