from __future__ import annotations

import textwrap
from typing import Any, Optional

from openai import AsyncOpenAI, OpenAIError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import Settings, settings


class Summarizer:
    def __init__(
        self,
        *,
        configuration: Settings,
    ) -> None:
        self._settings = configuration
        self._client: AsyncOpenAI | None = None

    @property
    def uses_llm(self) -> bool:
        return bool(self._settings.llm_api_key)

    def _get_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client

        api_key = self._settings.llm_api_key
        if not api_key:
            raise ValueError("LLM API key is not configured.")

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._settings.llm_base_url,
        )
        return self._client

    async def summarize(self, title: str, abstract: str) -> str:
        if not abstract:
            return ""
        if not self.uses_llm:
            return ""

        prompt = textwrap.dedent(
            f"""
            你是一位研究助理。请用{self._settings.summary_language}总结下面的arXiv论文摘要，给出{self._settings.summary_sentence_count}条要点列表，突出贡献、方法与潜在应用。
            标题: {title}
            摘要: {abstract}
            """
        ).strip()

        client = self._get_client()

        async for attempt in AsyncRetrying(
            wait=wait_exponential(multiplier=1, min=1, max=10),
            stop=stop_after_attempt(3),
            reraise=True,
            retry=retry_if_exception_type(OpenAIError),
        ):
            with attempt:
                response = await client.chat.completions.create(
                    model=self._settings.llm_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant specialized in summarizing arXiv papers.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    timeout=self._settings.request_timeout_seconds,
                )
                summary_text = self._extract_text(response)
                if summary_text:
                    return summary_text.strip()

        return ""

    def _extract_text(self, payload: Any) -> str:
        if payload is None:
            return ""

        choices = getattr(payload, "choices", None)
        if choices:
            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            if message is not None:
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    return content
                if isinstance(content, list) and content:
                    # Some providers return structured segments
                    return "".join(part.get("text", "") for part in content if isinstance(part, dict))

        if isinstance(payload, dict):
            return str(
                payload.get("text")
                or payload.get("summary")
                or payload.get("output")
                or ""
            )
        return str(payload)


def get_summarizer(settings_override: Optional[Settings] = None) -> Summarizer:
    return Summarizer(configuration=settings_override or settings)
