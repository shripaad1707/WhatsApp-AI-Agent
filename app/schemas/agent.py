import enum

from pydantic import BaseModel, Field


class Intent(str, enum.Enum):
    ORDER_STATUS = "order_status"
    REFUND_REQUEST = "refund_request"
    PRODUCT_INQUIRY = "product_inquiry"
    GENERAL_FAQ = "general_faq"
    COMPLAINT = "complaint"
    OTHER = "other"


class AgentOutput(BaseModel):
    """The agent's structured final answer - never free text handed straight to the
    customer. Validated before anything is sent; a fallback (escalate to human) applies
    if the model doesn't comply with this schema."""

    reply_text: str = Field(description="The message to send back to the customer.")
    confidence: float = Field(ge=0.0, le=1.0, description="The agent's own confidence in this response.")
    intent: Intent = Field(description="The intent detected in the customer's message.")
    tools_called: list[str] = Field(default_factory=list, description="Names of tools invoked while answering.")
    recommend_handoff: bool = Field(
        description="Whether the agent itself thinks a human should take over. This is "
        "advisory only - the Decision Engine, not the agent, makes the final call."
    )
    handoff_reason: str | None = Field(default=None, description="Why the agent recommends handoff, if it does.")
