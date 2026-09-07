import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import get_chat_model
from app.config import Settings, get_settings
from app.db.base import get_session
from app.schemas.whatsapp import InboundWhatsAppMessage
from app.services.embeddings import EmbeddingService
from app.services.pipeline import handle_inbound_message
from app.services.whatsapp import WhatsAppService

logger = structlog.get_logger(__name__)
router = APIRouter()

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _public_url(request: Request) -> str:
    """Reconstructs the URL Twilio actually POSTed to for signature validation.

    Local dev tunnels (ngrok, VS Code port forwarding, etc.) terminate TLS at a public
    hostname and forward to uvicorn as plain HTTP on localhost - so BOTH the scheme and
    the host in request.url are wrong unless we honor X-Forwarded-Proto/-Host. Fixing
    only the scheme (as an earlier version of this function did) still leaves the host
    as "localhost:PORT" instead of the public tunnel hostname Twilio actually signed
    against, so every signature check still fails even with a correct auth token.
    """
    url = request.url
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto and forwarded_proto != url.scheme:
        url = url.replace(scheme=forwarded_proto)
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host and forwarded_host != url.netloc:
        url = url.replace(netloc=forwarded_host)
    return str(url)


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    form = await request.form()
    form_dict = dict(form)

    whatsapp = WhatsAppService()
    signature = request.headers.get("X-Twilio-Signature", "")
    if settings.environment != "development" or signature:
        if not whatsapp.validate_signature(_public_url(request), form_dict, signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    inbound = InboundWhatsAppMessage.from_form(form_dict)
    if not inbound.from_number or not inbound.body:
        raise HTTPException(status_code=400, detail="Missing From/Body in webhook payload")

    embedder = EmbeddingService()
    chat_model = get_chat_model()

    try:
        result = await handle_inbound_message(
            session=session,
            inbound=inbound,
            whatsapp=whatsapp,
            embedder=embedder,
            chat_model=chat_model,
            settings=settings,
        )
        logger.info("webhook_processed", **{k: v for k, v in result.items() if k != "reply_text"})
    except Exception:
        await session.rollback()
        logger.exception("webhook_processing_failed", from_number=inbound.from_number)
        raise

    return Response(content=EMPTY_TWIML, media_type="application/xml")
