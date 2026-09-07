"""Owns all Twilio WhatsApp API calls - the only module that talks to Twilio directly."""

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.config import get_settings

logger = structlog.get_logger(__name__)


def _ensure_whatsapp_prefix(number: str) -> str:
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


class WhatsAppService:
    def __init__(self) -> None:
        settings = get_settings()
        self._from_number = _ensure_whatsapp_prefix(settings.twilio_whatsapp_from)
        self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self._validator = RequestValidator(settings.twilio_auth_token)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(TwilioRestException),
        reraise=True,
    )
    def send_message(self, to_number: str, body: str) -> str:
        """Sends a WhatsApp message via Twilio. Returns the outbound message SID."""
        message = self._client.messages.create(
            from_=self._from_number, to=_ensure_whatsapp_prefix(to_number), body=body
        )
        logger.info("whatsapp_message_sent", to=to_number, sid=message.sid)
        return message.sid

    def validate_signature(self, url: str, params: dict, signature: str) -> bool:
        """Verifies the X-Twilio-Signature header so the webhook only accepts requests from Twilio."""
        return self._validator.validate(url, params, signature)
