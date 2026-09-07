import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return await self.session.get(Product, product_id)

    async def get_by_sku(self, sku: str) -> Product | None:
        result = await self.session.execute(select(Product).where(Product.sku == sku))
        return result.scalar_one_or_none()

    async def search(self, query: str, limit: int = 10) -> list[Product]:
        like = f"%{query}%"
        result = await self.session.execute(
            select(Product)
            .where(or_(Product.name.ilike(like), Product.category.ilike(like), Product.description.ilike(like)))
            .limit(limit)
        )
        return list(result.scalars().all())
