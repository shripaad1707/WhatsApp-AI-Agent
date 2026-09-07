"""Owns all Gemini embedding calls.

Known gotcha (from a prior project): output_dimensionality truncation via the API
config doesn't always take effect depending on the installed client library version.
We ask for it, but always also truncate + renormalize manually as a safety net -
Matryoshka-trained embedding models like gemini-embedding-001 support truncating a
longer vector to a shorter prefix and renormalizing, with only a small quality cost.
"""

import math

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings


def _truncate_and_normalize(vector: list[float], dimensions: int) -> list[float]:
    truncated = vector[:dimensions]
    norm = math.sqrt(sum(x * x for x in truncated))
    if norm == 0:
        return truncated
    return [x / norm for x in truncated]


class EmbeddingService:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_embedding_model
        self._dimensions = settings.embedding_dimensions

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        response = self._client.models.embed_content(
            model=self._model,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=self._dimensions,
                task_type=task_type,
            ),
        )
        raw_vector = list(response.embeddings[0].values)
        if len(raw_vector) == self._dimensions:
            return raw_vector
        return _truncate_and_normalize(raw_vector, self._dimensions)

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text, task_type="RETRIEVAL_QUERY")
