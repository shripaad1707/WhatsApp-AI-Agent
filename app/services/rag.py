import asyncio

from app.repositories.kb_repo import KBRepository
from app.services.embeddings import EmbeddingService


async def retrieve_policy_context(kb_repo: KBRepository, embedder: EmbeddingService, query: str, top_k: int = 4) -> str:
    """Embeds the customer's message and retrieves the most relevant policy chunks -
    this is the only source of policy grounding handed to the agent."""
    query_embedding = await asyncio.to_thread(embedder.embed_query, query)
    chunks = await kb_repo.similarity_search(query_embedding, top_k=top_k)
    if not chunks:
        return ""
    return "\n\n".join(f"[{chunk.section}]\n{chunk.content}" for chunk in chunks)
