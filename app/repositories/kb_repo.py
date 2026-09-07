from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KBChunk


class KBRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_chunk(self, source: str, content: str, embedding: list[float], section: str | None = None) -> KBChunk:
        chunk = KBChunk(source=source, section=section, content=content, embedding=embedding)
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def clear_source(self, source: str) -> None:
        result = await self.session.execute(select(KBChunk).where(KBChunk.source == source))
        for chunk in result.scalars().all():
            await self.session.delete(chunk)
        await self.session.flush()

    async def similarity_search(self, query_embedding: list[float], top_k: int = 4) -> list[KBChunk]:
        result = await self.session.execute(
            select(KBChunk).order_by(KBChunk.embedding.cosine_distance(query_embedding)).limit(top_k)
        )
        return list(result.scalars().all())
