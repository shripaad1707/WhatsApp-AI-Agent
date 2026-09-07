"""The genuine ReAct-style tool-calling agent: the model decides which tool(s) to call,
in what order, looping until it has enough to answer - not a fixed sequence of edges.

Built as a hand-rolled LangGraph StateGraph rather than langgraph.prebuilt.create_react_agent
so we can (a) capture each tool's structured artifact (not just its text) for the Decision
Engine downstream, and (b) run a second structured-output pass to shape the final answer
into the required Pydantic schema.
"""

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from app.agent.prompts import STRUCTURED_OUTPUT_INSTRUCTIONS
from app.agent.state import AgentState
from app.schemas.agent import AgentOutput, Intent

logger = structlog.get_logger(__name__)

MAX_AGENT_TURNS = 6

_FALLBACK_OUTPUT = AgentOutput(
    reply_text=(
        "Thanks for reaching out - I want to make sure you get the right answer, so "
        "I'm connecting you with a member of our team."
    ),
    confidence=0.0,
    intent=Intent.OTHER,
    tools_called=[],
    recommend_handoff=True,
    handoff_reason="Agent failed to produce a valid structured response.",
)


def build_agent_graph(model: BaseChatModel, tools: list[BaseTool]):
    model_with_tools = model.bind_tools(tools)
    structured_model = model.with_structured_output(AgentOutput)
    tools_by_name = {t.name: t for t in tools}

    async def agent_node(state: AgentState) -> dict:
        response = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response], "turn_count": 1}

    async def tools_node(state: AgentState) -> dict:
        last_message: AIMessage = state["messages"][-1]
        tool_messages: list[ToolMessage] = []
        artifacts: dict = {}

        for call in last_message.tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                tool_messages.append(
                    ToolMessage(content=f"Unknown tool '{call['name']}'", tool_call_id=call["id"])
                )
                continue
            try:
                result_message: ToolMessage = await tool.ainvoke(call)
            except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
                logger.warning("tool_call_failed", tool=call["name"], error=str(exc))
                result_message = ToolMessage(content=f"Tool error: {exc}", tool_call_id=call["id"])

            tool_messages.append(result_message)
            if result_message.artifact is not None:
                artifacts[call["name"]] = result_message.artifact

        return {"messages": tool_messages, "tool_artifacts": artifacts}

    def route_after_agent(state: AgentState) -> str:
        last_message: AIMessage = state["messages"][-1]
        if getattr(last_message, "tool_calls", None) and state["turn_count"] < MAX_AGENT_TURNS:
            return "tools"
        return "finalize"

    async def finalize_node(state: AgentState) -> dict:
        finalize_messages = list(state["messages"]) + [HumanMessage(content=STRUCTURED_OUTPUT_INSTRUCTIONS)]
        try:
            result = await structured_model.ainvoke(finalize_messages)
            if not isinstance(result, AgentOutput):
                result = AgentOutput.model_validate(result)
        except Exception as exc:  # noqa: BLE001 - malformed structured output must not reach the customer
            logger.error("structured_output_invalid", error=str(exc))
            result = _FALLBACK_OUTPUT
        return {"agent_output": result}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "finalize": "finalize"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)

    return graph.compile()


async def run_agent(
    model: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
    history: list[BaseMessage],
    customer_message: str,
) -> tuple[AgentOutput, dict]:
    """Runs the agent loop. Returns (structured output, tool artifacts by tool name)."""
    graph = build_agent_graph(model, tools)
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt), *history, HumanMessage(content=customer_message)]

    final_state = await graph.ainvoke(
        {"messages": messages, "tool_artifacts": {}, "turn_count": 0, "agent_output": None}
    )

    agent_output: AgentOutput = final_state.get("agent_output") or _FALLBACK_OUTPUT
    return agent_output, final_state.get("tool_artifacts", {})
