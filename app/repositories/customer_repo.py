import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Customer


class CustomerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        return await self.session.get(Customer, customer_id)

    async def get_by_whatsapp_number(self, whatsapp_number: str) -> Customer | None:
        result = await self.session.execute(
            select(Customer).where(Customer.whatsapp_number == whatsapp_number)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, whatsapp_number: str, name: str | None = None) -> Customer:
        customer = await self.get_by_whatsapp_number(whatsapp_number)
        if customer:
            return customer
        customer = Customer(whatsapp_number=whatsapp_number, name=name or whatsapp_number)
        self.session.add(customer)
        await self.session.flush()
        return customer

    async def update_long_term_memory(
        self, customer_id: uuid.UUID, issue_summary: str | None = None, preferences: dict | None = None
    ) -> Customer | None:
        customer = await self.get_by_id(customer_id)
        if customer is None:
            return None
        if issue_summary is not None:
            customer.issue_summary = issue_summary
        if preferences is not None:
            customer.preferences = {**customer.preferences, **preferences}
        await self.session.flush()
        return customer
