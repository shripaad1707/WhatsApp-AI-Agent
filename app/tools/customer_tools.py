from langchain_core.tools import tool

from app.repositories.customer_repo import CustomerRepository
from app.tools.context import ToolContext, tool_result


def build_customer_tools(ctx: ToolContext) -> list:
    @tool(response_format="content_and_artifact")
    async def get_my_profile() -> tuple[str, dict]:
        """Look up the identified customer's own profile: name, email, known preferences,
        and a summary of past issues. Use this to personalize responses or recall context
        from previous conversations. Takes no arguments - it always returns the current
        customer's own record."""
        async with ctx.audit_repo.timed_tool_call(ctx.conversation_id, "get_my_profile", {}) as rec:
            repo = CustomerRepository(ctx.session)
            customer = await repo.get_by_id(ctx.customer_id)
            if customer is None:
                rec.result = {"found": False}
                return tool_result(rec.result)
            rec.result = {
                "found": True,
                "name": customer.name,
                "email": customer.email,
                "preferences": customer.preferences,
                "issue_summary": customer.issue_summary,
            }
            return tool_result(rec.result)

    return [get_my_profile]
