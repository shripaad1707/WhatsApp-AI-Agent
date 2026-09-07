from app.decision_engine.engine import DecisionEngine
from app.decision_engine.rules import wants_human
from app.schemas.agent import AgentOutput, Intent
from app.tools.refund_policy import RefundEligibility


def make_output(**overrides) -> AgentOutput:
    defaults = dict(
        reply_text="Here is your order status.",
        confidence=0.9,
        intent=Intent.ORDER_STATUS,
        tools_called=["lookup_order"],
        recommend_handoff=False,
        handoff_reason=None,
    )
    defaults.update(overrides)
    return AgentOutput(**defaults)


def test_wants_human_detects_common_phrasings():
    assert wants_human("I want to talk to a human please")
    assert wants_human("can I speak with an agent")
    assert wants_human("connect me to a representative")
    assert wants_human("let me talk to your MANAGER")


def test_wants_human_does_not_false_positive_on_unrelated_text():
    assert not wants_human("where is my order")
    assert not wants_human("I want a refund for humanely made products")


def test_explicit_human_request_always_escalates():
    engine = DecisionEngine(confidence_threshold=0.75, high_value_threshold=200.0)
    decision = engine.evaluate("I want to talk to a human", make_output(confidence=0.99))
    assert decision.should_handoff
    assert "human" in decision.reason.lower()


def test_low_confidence_escalates():
    engine = DecisionEngine(confidence_threshold=0.75, high_value_threshold=200.0)
    decision = engine.evaluate("where is my order", make_output(confidence=0.5))
    assert decision.should_handoff


def test_high_value_order_escalates():
    engine = DecisionEngine(confidence_threshold=0.75, high_value_threshold=200.0)
    decision = engine.evaluate("where is my order", make_output(confidence=0.95), order_value=500.0)
    assert decision.should_handoff


def test_ambiguous_refund_escalates():
    engine = DecisionEngine(confidence_threshold=0.75, high_value_threshold=200.0)
    decision = engine.evaluate(
        "I want a refund",
        make_output(confidence=0.9, intent=Intent.REFUND_REQUEST),
        order_value=50.0,
        refund_eligibility=RefundEligibility.AMBIGUOUS,
    )
    assert decision.should_handoff


def test_eligible_refund_under_threshold_auto_approves():
    engine = DecisionEngine(confidence_threshold=0.75, high_value_threshold=200.0)
    decision = engine.evaluate(
        "I want a refund",
        make_output(confidence=0.9, intent=Intent.REFUND_REQUEST),
        order_value=50.0,
        refund_eligibility=RefundEligibility.ELIGIBLE,
    )
    assert not decision.should_handoff
    assert decision.auto_process_refund


def test_eligible_refund_over_threshold_still_escalates():
    engine = DecisionEngine(confidence_threshold=0.75, high_value_threshold=200.0)
    decision = engine.evaluate(
        "I want a refund",
        make_output(confidence=0.9, intent=Intent.REFUND_REQUEST),
        order_value=999.0,
        refund_eligibility=RefundEligibility.ELIGIBLE,
    )
    assert decision.should_handoff
    assert not decision.auto_process_refund


def test_normal_reply_does_not_escalate():
    engine = DecisionEngine(confidence_threshold=0.75, high_value_threshold=200.0)
    decision = engine.evaluate("where is my order", make_output(confidence=0.9))
    assert not decision.should_handoff
