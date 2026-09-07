from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.db.models import Message, MessageSender


def messages_to_langchain(messages: list[Message]) -> list[BaseMessage]:
    """Short-term memory: the last N messages from the conversations table, as-is -
    no separate memory service, just this query's output reshaped for the LLM."""
    history: list[BaseMessage] = []
    for message in messages:
        if message.sender == MessageSender.CUSTOMER:
            history.append(HumanMessage(content=message.content))
        else:
            history.append(AIMessage(content=message.content))
    return history
