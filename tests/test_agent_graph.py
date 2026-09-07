"""Structural smoke test for the hand-rolled LangGraph loop in app/agent/graph.py -
verifies the agent/tools/finalize wiring and artifact plumbing without calling a real LLM.
"""
import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.agent.graph import run_agent
from app.schemas.agent import AgentOutput, Intent


@tool(response_format="content_and_artifact")
async def fake_lookup_order(order_number: str) -> tuple:
    """Looks up a fake order."""
    return (f"Order {order_number} is in_transit", {"found": True, "status": "in_transit", "order_total": 42.0})


class _FakeBoundModel:
    def __init__(self, script: list[AIMessage]):
        self._script = list(script)

    async def ainvoke(self, messages):
        return self._script.pop(0)


class _FakeStructuredModel:
    def __init__(self, output: AgentOutput):
        self._output = output

    async def ainvoke(self, messages):
        return self._output


class FakeModel:
    """Duck-types the two BaseChatModel methods app/agent/graph.py actually calls."""

    def __init__(self, tool_call_script: list[AIMessage], structured_output: AgentOutput):
        self._tool_call_script = tool_call_script
        self._structured_output = structured_output

    def bind_tools(self, tools):
        return _FakeBoundModel(self._tool_call_script)

    def with_structured_output(self, schema):
        return _FakeStructuredModel(self._structured_output)


@pytest.mark.asyncio
async def test_agent_loop_calls_tool_then_finalizes():
    tool_call_ai_message = AIMessage(
        content="",
        tool_calls=[{"name": "fake_lookup_order", "args": {"order_number": "ORD-1"}, "id": "call_1", "type": "tool_call"}],
    )
    final_ai_message = AIMessage(content="Your order ORD-1 is in transit.")
    expected_output = AgentOutput(
        reply_text="Your order ORD-1 is in transit.",
        confidence=0.95,
        intent=Intent.ORDER_STATUS,
        tools_called=["fake_lookup_order"],
        recommend_handoff=False,
    )

    model = FakeModel(
        tool_call_script=[tool_call_ai_message, final_ai_message],
        structured_output=expected_output,
    )

    output, artifacts = await run_agent(
        model=model,
        tools=[fake_lookup_order],
        system_prompt="system",
        history=[],
        customer_message="where is my order ORD-1",
    )

    assert output == expected_output
    assert artifacts["fake_lookup_order"]["status"] == "in_transit"
    assert artifacts["fake_lookup_order"]["order_total"] == 42.0


@pytest.mark.asyncio
async def test_agent_loop_with_no_tool_calls_goes_straight_to_finalize():
    final_ai_message = AIMessage(content="We only ship within the US.")
    expected_output = AgentOutput(
        reply_text="We only ship within the US.",
        confidence=0.9,
        intent=Intent.GENERAL_FAQ,
        tools_called=[],
        recommend_handoff=False,
    )
    model = FakeModel(tool_call_script=[final_ai_message], structured_output=expected_output)

    output, artifacts = await run_agent(
        model=model,
        tools=[fake_lookup_order],
        system_prompt="system",
        history=[],
        customer_message="do you ship internationally?",
    )

    assert output == expected_output
    assert artifacts == {}
