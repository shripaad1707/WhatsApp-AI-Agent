from datetime import datetime, timedelta, timezone

from app.db.models import OrderStatus
from app.tools.refund_policy import RefundEligibility, check_refund_eligibility

NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


def test_eligible_within_window():
    result = check_refund_eligibility(
        OrderStatus.DELIVERED, NOW - timedelta(days=10), now=NOW
    )
    assert result.eligibility == RefundEligibility.ELIGIBLE
    assert result.days_since_delivery == 10


def test_ineligible_outside_window():
    result = check_refund_eligibility(
        OrderStatus.DELIVERED, NOW - timedelta(days=45), now=NOW
    )
    assert result.eligibility == RefundEligibility.INELIGIBLE
    assert "outside" in result.reason


def test_ineligible_already_refunded():
    result = check_refund_eligibility(OrderStatus.REFUNDED, NOW - timedelta(days=5), now=NOW)
    assert result.eligibility == RefundEligibility.INELIGIBLE


def test_ineligible_not_yet_delivered():
    result = check_refund_eligibility(OrderStatus.IN_TRANSIT, None, now=NOW)
    assert result.eligibility == RefundEligibility.INELIGIBLE


def test_ambiguous_missing_delivery_date():
    result = check_refund_eligibility(OrderStatus.DELIVERED, None, now=NOW)
    assert result.eligibility == RefundEligibility.AMBIGUOUS


def test_delivered_refund_requested_within_window_is_eligible():
    result = check_refund_eligibility(
        OrderStatus.DELIVERED_REFUND_REQUESTED, NOW - timedelta(days=1), now=NOW
    )
    assert result.eligibility == RefundEligibility.ELIGIBLE


def test_exactly_on_boundary_is_eligible():
    result = check_refund_eligibility(
        OrderStatus.DELIVERED, NOW - timedelta(days=30), now=NOW
    )
    assert result.eligibility == RefundEligibility.ELIGIBLE


def test_one_day_past_boundary_is_ineligible():
    result = check_refund_eligibility(
        OrderStatus.DELIVERED, NOW - timedelta(days=31), now=NOW
    )
    assert result.eligibility == RefundEligibility.INELIGIBLE
