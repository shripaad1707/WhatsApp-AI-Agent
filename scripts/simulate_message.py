"""Simulates an inbound WhatsApp message through the full pipeline without needing a
live Twilio webhook - useful for demoing/testing the two required end-to-end scenarios
against seeded data. Twilio sends are stubbed to print instead of calling the real API
(pass --live to actually send via Twilio once TWILIO_* env vars are set).

Usage:
    python -m scripts.simulate_message --phone "whatsapp:+15551000000" --message "where is my order?"
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.llm import get_chat_model
from app.config import get_settings
from app.db.base import async_session_factory
from app.schemas.whatsapp import InboundWhatsAppMessage
from app.services.embeddings import EmbeddingService
from app.services.pipeline import handle_inbound_message
from app.services.whatsapp import WhatsAppService


class DryRunWhatsAppService(WhatsAppService):
    def send_message(self, to_number: str, body: str) -> str:
        print(f"\n--- [DRY RUN] WhatsApp -> {to_number} ---\n{body}\n---------------------------------\n")
        return "DRYRUN-SID"


async def main(phone: str, message: str, live: bool) -> None:
    settings = get_settings()
    whatsapp = WhatsAppService() if live else DryRunWhatsAppService()
    embedder = EmbeddingService()
    chat_model = get_chat_model()

    inbound = InboundWhatsAppMessage(
        message_sid=f"SIM{abs(hash(message)) % 100000}",
        from_number=phone,
        to_number=settings.twilio_whatsapp_from or "whatsapp:+14155238886",
        body=message,
    )

    async with async_session_factory() as session:
        result = await handle_inbound_message(
            session=session,
            inbound=inbound,
            whatsapp=whatsapp,
            embedder=embedder,
            chat_model=chat_model,
            settings=settings,
        )

    print("Pipeline result:", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True, help="e.g. 'whatsapp:+15551000000' (must match a seeded customer)")
    parser.add_argument("--message", required=True)
    parser.add_argument("--live", action="store_true", help="Actually send via Twilio instead of dry-run printing.")
    args = parser.parse_args()
    asyncio.run(main(args.phone, args.message, args.live))
