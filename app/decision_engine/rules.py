"""Deterministic pattern checks - never an LLM guess. Pure functions, independently testable."""

import re

_HUMAN_REQUEST_PATTERNS = [
    r"\bhuman\b",
    r"\breal\s+person\b",
    r"\bactual\s+person\b",
    r"\btalk\s+to\s+(a\s+|an\s+)?(person|agent|human|someone|representative)\b",
    r"\bspeak\s+(to|with)\s+(a\s+|an\s+)?(person|agent|human|someone|representative)\b",
    r"\bcustomer\s+service\s+rep(resentative)?\b",
    r"\bconnect\s+me\s+(to|with)\b",
    r"\bescalate\b",
    r"\bmanager\b",
    r"\blive\s+agent\b",
]

_HUMAN_REQUEST_RE = re.compile("|".join(_HUMAN_REQUEST_PATTERNS), re.IGNORECASE)


def wants_human(message_text: str) -> bool:
    """True if the customer's message explicitly asks for a human agent."""
    return bool(_HUMAN_REQUEST_RE.search(message_text))
