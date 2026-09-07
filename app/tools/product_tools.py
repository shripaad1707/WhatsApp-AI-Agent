from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.repositories.product_repo import ProductRepository
from app.tools.context import ToolContext, tool_result


class SearchProductsInput(BaseModel):
    query: str = Field(description="A search term - product name, category, or keyword.")


def build_product_tools(ctx: ToolContext) -> list:
    @tool(args_schema=SearchProductsInput, response_format="content_and_artifact")
    async def search_products(query: str) -> tuple[str, dict]:
        """Search the product catalog by name, category, or keyword. Use this when the
        customer asks about a product, availability, or price - the catalog is public
        and not scoped to any particular customer."""
        async with ctx.audit_repo.timed_tool_call(
            ctx.conversation_id, "search_products", {"query": query}
        ) as rec:
            repo = ProductRepository(ctx.session)
            products = await repo.search(query)
            rec.result = {
                "products": [
                    {
                        "sku": p.sku,
                        "name": p.name,
                        "category": p.category,
                        "price": float(p.price),
                        "in_stock": p.stock_quantity > 0,
                    }
                    for p in products
                ]
            }
            return tool_result(rec.result)

    return [search_products]
