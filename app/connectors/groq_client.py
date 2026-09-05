import logging
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.config import settings

logger = logging.getLogger("orca")


class GroqClient:
    def __init__(self) -> None:
        self._api_key = settings.GROQ_API_KEY
        self._model = settings.GROQ_MODEL
        self._base_url = "https://api.groq.com/openai/v1"
        self._client: AsyncOpenAI | None = None

    def _ensure_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GROQ_API_KEY is not configured")
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        client = self._ensure_client()
        used_model = model or self._model

        logger.debug(
            "Sending chat request to Groq",
            extra={
                "model": used_model,
                "message_count": len(messages),
            },
        )

        try:
            response = await client.chat.completions.create(
                model=used_model,
                messages=messages,
                **kwargs,
            )
        except Exception as exc:
            logger.error("Groq chat request failed", exc_info=True)
            raise RuntimeError(f"Groq request failed: {exc}") from exc

        return response

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


groq_client = GroqClient()
