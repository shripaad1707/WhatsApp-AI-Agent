"""Generates synthetic demo data: customers, products, orders, order_items, tickets.

Run with: python -m scripts.seed_data
"""
import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker

from app.db.base import async_session_factory
from app.db.models import (
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    Ticket,
    TicketPriority,
    TicketStatus,
    TicketType,
)

fake = Faker()
Faker.seed(42)
random.seed(42)

NUM_CUSTOMERS = 18
NUM_PRODUCTS = 26
NUM_ORDERS = 36
REFUND_WINDOW_DAYS = 30
HIGH_VALUE_THRESHOLD = 200.00

CATEGORIES = {
    "Headphones": (29.99, 249.99),
    "Smartwatches": (89.99, 399.99),
    "Laptop Accessories": (14.99, 129.99),
    "Home Speakers": (39.99, 349.99),
    "Phone Cases": (9.99, 39.99),
    "Chargers & Cables": (7.99, 49.99),
    "Keyboards & Mice": (19.99, 149.99),
    "Cameras": (99.99, 599.99),
}

STATUS_WEIGHTS = [
    (OrderStatus.DELIVERED, 0.40),
    (OrderStatus.IN_TRANSIT, 0.20),
    (OrderStatus.PROCESSING, 0.15),
    (OrderStatus.DELIVERED_REFUND_REQUESTED, 0.15),
    (OrderStatus.REFUNDED, 0.05),
    (OrderStatus.CANCELLED, 0.05),
]


def weighted_status() -> OrderStatus:
    statuses, weights = zip(*STATUS_WEIGHTS)
    return random.choices(statuses, weights=weights, k=1)[0]


def make_whatsapp_number(i: int) -> str:
    # Twilio WhatsApp sandbox format: "whatsapp:+1XXXXXXXXXX"
    return f"whatsapp:+1555{100000 + i:06d}"


async def seed() -> None:
    async with async_session_factory() as session:
        # --- Products ---
        products: list[Product] = []
        for _ in range(NUM_PRODUCTS):
            category = random.choice(list(CATEGORIES.keys()))
            low, high = CATEGORIES[category]
            product = Product(
                sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
                name=f"{fake.color_name()} {category[:-1] if category.endswith('s') else category} {fake.word().capitalize()}",
                description=fake.sentence(nb_words=12),
                category=category,
                price=round(random.uniform(low, high), 2),
                stock_quantity=random.randint(0, 500),
            )
            products.append(product)
        session.add_all(products)
        await session.flush()

        # --- Customers ---
        customers: list[Customer] = []
        for i in range(NUM_CUSTOMERS):
            customer = Customer(
                whatsapp_number=make_whatsapp_number(i),
                name=fake.name(),
                email=fake.email(),
                preferences={},
            )
            customers.append(customer)
        session.add_all(customers)
        await session.flush()

        # --- Orders + order_items ---
        orders: list[Order] = []
        now = datetime.now(timezone.utc)
        for i in range(NUM_ORDERS):
            customer = random.choice(customers)
            status = weighted_status()

            # Deliberately push a few orders outside the refund window,
            # and a few above the high-value threshold, so both escalation
            # and ineligibility paths have real data to exercise.
            if i < 6:
                order_date = now - timedelta(days=random.randint(45, 120))  # outside refund window
            else:
                order_date = now - timedelta(days=random.randint(0, 25))

            delivered_at = None
            if status in (OrderStatus.DELIVERED, OrderStatus.DELIVERED_REFUND_REQUESTED, OrderStatus.REFUNDED):
                delivered_at = order_date + timedelta(days=random.randint(2, 6))

            n_items = random.randint(1, 4)
            chosen_products = random.sample(products, n_items)
            force_high_value = i < 8  # first 8 orders skew high-value to test the threshold path

            items_data = []
            total = 0.0
            for product in chosen_products:
                qty = random.randint(1, 3)
                unit_price = float(product.price)
                if force_high_value:
                    unit_price = max(unit_price, HIGH_VALUE_THRESHOLD)
                items_data.append((product, qty, unit_price))
                total += unit_price * qty

            order = Order(
                customer_id=customer.id,
                order_number=f"ORD-{100000 + i}",
                status=status,
                total_amount=round(total, 2),
                currency="USD",
                tracking_number=(f"TRK{uuid.uuid4().hex[:10].upper()}" if status != OrderStatus.PROCESSING else None),
                order_date=order_date,
                delivered_at=delivered_at,
            )
            session.add(order)
            await session.flush()

            for product, qty, unit_price in items_data:
                session.add(
                    OrderItem(order_id=order.id, product_id=product.id, quantity=qty, unit_price=unit_price)
                )

            orders.append(order)

        await session.flush()

        # --- A few pre-existing tickets ---
        refund_requested_orders = [o for o in orders if o.status == OrderStatus.DELIVERED_REFUND_REQUESTED]
        for order in refund_requested_orders[:5]:
            session.add(
                Ticket(
                    customer_id=order.customer_id,
                    order_id=order.id,
                    subject=f"Refund request for {order.order_number}",
                    ticket_type=TicketType.REFUND_REQUEST,
                    status=random.choice([TicketStatus.OPEN, TicketStatus.PENDING]),
                    priority=TicketPriority.NORMAL,
                    description="Customer requested a refund via WhatsApp.",
                )
            )

        session.add(
            Ticket(
                customer_id=customers[0].id,
                subject="General inquiry about loyalty program",
                ticket_type=TicketType.GENERAL,
                status=TicketStatus.RESOLVED,
                priority=TicketPriority.LOW,
                description="Customer asked about a loyalty/rewards program.",
                resolution_notes="Explained there is no loyalty program currently.",
            )
        )

        await session.commit()

        print(f"Seeded {len(customers)} customers, {len(products)} products, {len(orders)} orders.")


if __name__ == "__main__":
    asyncio.run(seed())
