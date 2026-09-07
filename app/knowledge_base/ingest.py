"""Chunks every .md file under knowledge_base/content/ and embeds it into kb_chunks.

Run with: python -m app.knowledge_base.ingest
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import structlog

from app.db.base import async_session_factory
from app.repositories.kb_repo import KBRepository
from app.services.embeddings import EmbeddingService

logger = structlog.get_logger(__name__)

CONTENT_DIR = Path(__file__).parent / "content"


def _split_faq_items(body: str) -> list[str]:
    # Each FAQ item starts with "N. **Question**"
    items = re.split(r"\n(?=\d+\.\s+\*\*)", body.strip())
    return [item.strip() for item in items if item.strip()]


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Returns a list of (section_label, chunk_text)."""
    chunks: list[tuple[str, str]] = []

    sections = re.split(r"\n(?=## )", text.strip())
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        section_title = lines[0].lstrip("# ").strip()
        body = "\n".join(lines[1:]).strip()

        if not body:
            continue

        if "Frequently Asked Questions" in section_title:
            for item in _split_faq_items(body):
                first_line = item.splitlines()[0]
                chunks.append((f"{section_title} - {first_line}"[:150], item))
            continue

        subsections = re.split(r"\n(?=### )", body)
        if len(subsections) > 1:
            for sub in subsections:
                sub_lines = sub.strip().splitlines()
                if not sub_lines:
                    continue
                sub_title = sub_lines[0].lstrip("# ").strip()
                sub_body = "\n".join(sub_lines[1:]).strip() or sub.strip()
                chunks.append((f"{section_title} > {sub_title}", f"## {section_title}\n### {sub_title}\n{sub_body}"))
        else:
            chunks.append((section_title, section.strip()))

    return chunks


async def ingest() -> None:
    embedder = EmbeddingService()
    md_files = sorted(CONTENT_DIR.glob("*.md"))

    async with async_session_factory() as session:
        kb_repo = KBRepository(session)

        for path in md_files:
            source_name = path.name
            text = path.read_text(encoding="utf-8")
            chunks = chunk_markdown(text)

            await kb_repo.clear_source(source_name)
            for section_label, chunk_text in chunks:
                embedding = embedder.embed(chunk_text)
                await kb_repo.add_chunk(
                    source=source_name, section=section_label, content=chunk_text, embedding=embedding
                )

            logger.info("kb_ingest_source_complete", source=source_name, chunks=len(chunks))
            print(f"Ingested {len(chunks)} chunks from {source_name}")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(ingest())
