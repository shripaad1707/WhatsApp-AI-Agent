import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.schemas.agent import AgentOutput


def _merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    tool_artifacts: Annotated[dict, _merge_dicts]
    turn_count: Annotated[int, operator.add]
    agent_output: AgentOutput | None
