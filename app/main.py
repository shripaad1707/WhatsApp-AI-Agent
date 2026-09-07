import structlog
from fastapi import FastAPI

from app.config import get_settings
from app.routers import conversations, escalations, tickets, webhook

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

settings = get_settings()

app = FastAPI(title="AI Customer Support & Sales Agent")

app.include_router(webhook.router)
app.include_router(conversations.router)
app.include_router(tickets.router)
app.include_router(escalations.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
