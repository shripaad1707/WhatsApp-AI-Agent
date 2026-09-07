import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Order, OrderItem, OrderStatus


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        result = await self.session.execute(
            select(Order).options(selectinload(Order.items).selectinload(OrderItem.product)).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_order_number(self, order_number: str) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items).selectinload(OrderItem.product))
            .where(Order.order_number == order_number)
        )
        return result.scalar_one_or_none()

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items).selectinload(OrderItem.product))
            .where(Order.customer_id == customer_id)
            .order_by(Order.order_date.desc())
        )
        return list(result.scalars().all())

    async def get_latest_for_customer(self, customer_id: uuid.UUID) -> Order | None:
        orders = await self.list_for_customer(customer_id)
        return orders[0] if orders else None

    async def mark_refunded(self, order_id: uuid.UUID) -> Order | None:
        """Deterministic status change applied by the Decision Engine after it approves
        an auto-processed refund - never called by the agent itself. A tracked status
        change for this demo, not a real payment-gateway reversal."""
        order = await self.get_by_id(order_id)
        if order is None:
            return None
        order.status = OrderStatus.REFUNDED
        await self.session.flush()
        return order
