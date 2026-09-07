"""The Decision Engine: plain deterministic Python, sitting AFTER the agent.

The LLM never decides whether to escalate - it only decides what to say and which
tools to call. This module makes the auto-reply-vs-human-handoff call using the rules
from the project brief, in a fixed priority order so the outcome is always explainable.
"""

from dataclasses import dataclass

from app.decision_engine.rules import wants_human
from app.schemas.agent import AgentOutput, Intent
from app.tools.refund_policy import RefundEligibility


@dataclass
class HandoffDecision:
    should_handoff: bool
    reason: str | None = None
    auto_process_refund: bool = False


class DecisionEngine:
    def __init__(self, confidence_threshold: float, high_value_threshold: float):
        self.confidence_threshold = confidence_threshold
        self.high_value_threshold = high_value_threshold

    def evaluate(
        self,
        customer_message: str,
        agent_output: AgentOutput,
        order_value: float | None = None,
        refund_eligibility: RefundEligibility | None = None,
    ) -> HandoffDecision:
        # 1. Explicit request for a human - deterministic keyword check, always wins.
        if wants_human(customer_message):
            return HandoffDecision(True, "Customer explicitly asked to speak with a human.")

        # 2. Agent's own reported confidence.
        if agent_output.confidence < self.confidence_threshold:
            return HandoffDecision(
                True,
                f"Agent confidence {agent_output.confidence:.2f} is below the "
                f"{self.confidence_threshold:.2f} threshold.",
            )

        # 3. High-value transaction/order - always human-reviewed.
        if order_value is not None and order_value > self.high_value_threshold:
            return HandoffDecision(
                True,
                f"Order/transaction value {order_value:.2f} exceeds the "
                f"{self.high_value_threshold:.2f} high-value threshold.",
            )

        # 4. Refund-specific rules: ambiguous eligibility always goes to a human.
        if agent_output.intent == Intent.REFUND_REQUEST and refund_eligibility is not None:
            if refund_eligibility == RefundEligibility.AMBIGUOUS:
                return HandoffDecision(True, "Refund eligibility is ambiguous under current policy.")
            if refund_eligibility == RefundEligibility.ELIGIBLE:
                # Eligible, under threshold, confidence is fine, no explicit human request:
                # auto-approve and let the pipeline execute the tracked status change.
                return HandoffDecision(False, auto_process_refund=True)

        # 5. Agent's own advisory recommendation, honored only if nothing else already decided.
        if agent_output.recommend_handoff:
            return HandoffDecision(True, agent_output.handoff_reason or "Agent recommended human handoff.")

        return HandoffDecision(False)
