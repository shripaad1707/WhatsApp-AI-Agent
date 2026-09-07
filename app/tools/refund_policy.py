"""Deterministic refund-eligibility policy - the agent never freelances this judgment.

Pure functions only (no DB/session dependency) so this is independently testable.
Must stay in sync with the return-window figure published in the knowledge base
(knowledge_base/content/policies.md).
"""

import enum
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.models import OrderStatus

REFUND_WINDOW_DAYS = 30

ELIGIBLE_STATUSES = {OrderStatus.DELIVERED, OrderStatus.DELIVERED_REFUND_REQUESTED}
TERMINAL_INELIGIBLE_STATUSES = {OrderStatus.REFUNDED, OrderStatus.CANCELLED}
NOT_YET_DELIVERED_STATUSES = {OrderStatus.PROCESSING, OrderStatus.IN_TRANSIT}


class RefundEligibility(str, enum.Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    AMBIGUOUS = "ambiguous"


@dataclass
class RefundEligibilityResult:
    eligibility: RefundEligibility
    reason: str
    days_since_delivery: int | None = None


def check_refund_eligibility(
    status: OrderStatus,
    delivered_at: datetime | None,
    now: datetime | None = None,
) -> RefundEligibilityResult:
    now = now or datetime.now(timezone.utc)

    if status in TERMINAL_INELIGIBLE_STATUSES:
        reason = (
            "This order has already been refunded."
            if status == OrderStatus.REFUNDED
            else "This order was cancelled before delivery, so there is nothing to refund."
        )
        return RefundEligibilityResult(RefundEligibility.INELIGIBLE, reason)

    if status in NOT_YET_DELIVERED_STATUSES:
        return RefundEligibilityResult(
            RefundEligibility.INELIGIBLE,
            "This order has not been delivered yet, so a refund cannot be processed until it arrives.",
        )

    if status not in ELIGIBLE_STATUSES:
        return RefundEligibilityResult(RefundEligibility.AMBIGUOUS, f"Unrecognized order status '{status}'.")

    if delivered_at is None:
        return RefundEligibilityResult(
            RefundEligibility.AMBIGUOUS,
            "Order is marked delivered but has no delivery date on record - needs human review.",
        )

    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=timezone.utc)

    days_since_delivery = (now - delivered_at).days

    if days_since_delivery > REFUND_WINDOW_DAYS:
        return RefundEligibilityResult(
            RefundEligibility.INELIGIBLE,
            f"Delivered {days_since_delivery} days ago, which is outside the {REFUND_WINDOW_DAYS}-day return window.",
            days_since_delivery,
        )

    return RefundEligibilityResult(
        RefundEligibility.ELIGIBLE,
        f"Delivered {days_since_delivery} days ago, within the {REFUND_WINDOW_DAYS}-day return window.",
        days_since_delivery,
    )
