from pydantic import BaseModel


class InboundWhatsAppMessage(BaseModel):
    """Parsed form of Twilio's inbound WhatsApp webhook payload."""

    message_sid: str
    from_number: str  # e.g. "whatsapp:+15551234567"
    to_number: str
    body: str
    profile_name: str | None = None
    num_media: int = 0

    @classmethod
    def from_form(cls, form: dict) -> "InboundWhatsAppMessage":
        return cls(
            message_sid=form.get("MessageSid", ""),
            from_number=form.get("From", ""),
            to_number=form.get("To", ""),
            body=form.get("Body", ""),
            profile_name=form.get("ProfileName"),
            num_media=int(form.get("NumMedia", 0) or 0),
        )
