from abc import ABC, abstractmethod

import truststore
from openai import AsyncOpenAI

from recipebox.config import settings


class Embedder(ABC):
    """Turns text into a fixed-size vector. The dimension must match EMBEDDING_DIM
    in models.py and the vector(N) column type in the migration."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...


class OpenAIEmbedder(Embedder):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        truststore.inject_into_ssl()
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model or settings.embedding_model

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=self._model, input=text)
        return resp.data[0].embedding
