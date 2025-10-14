from __future__ import annotations

import textwrap
from typing import Any, List, Optional

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

    async def summarize(self, title: str, abstract: str, *, full_text: str | None = None) -> str:
        document = (full_text or "").strip()
        abstract = abstract.strip()
        if not document:
            document = abstract
        if not document:
            return ""
        if not self.uses_llm:
            return ""

        segments = self._chunk_text(document)
        total_segments = len(segments)

        if total_segments <= 1:
            prompt = textwrap.dedent(
                f"""
                你是一位研究助理。请用{self._settings.summary_language}总结下面的arXiv论文全文内容，
                给出{self._settings.summary_sentence_count}条要点列表，突出贡献、方法，并简要说明实验结果。
                标题: {title}
                正文: {segments[0] if segments else document}
                """
            ).strip()
            return await self._call_llm(prompt)

        summaries: List[str] = []
        max_chunks = max(1, self._settings.full_text_max_chunks)
        limited_segments = segments[:max_chunks]
        for index, segment in enumerate(limited_segments, start=1):
            prompt = textwrap.dedent(
                f"""
                你是一位研究助理，正在阅读一篇arXiv论文的部分内容。
                请用{self._settings.summary_language}简要提炼该部分的关键信息，
                包括核心问题、主要方法、关键实验或理论结果以及与全篇的关系。
                请输出3条以内的要点列表。
                标题: {title}
                篇章进度: 第{index}段，共{total_segments}段（分析前{max_chunks}段）。
                章节内容:
                {segment}
                """
            ).strip()
            summary = await self._call_llm(prompt)
            if summary:
                summaries.append(summary.strip())

        if not summaries:
            prompt = textwrap.dedent(
                f"""
                你是一位研究助理。请用{self._settings.summary_language}总结下面的arXiv论文内容，
                给出{self._settings.summary_sentence_count}条要点列表，突出贡献、方法，并简要说明实验结果。
                标题: {title}
                正文: {document}
                """
            ).strip()
            return await self._call_llm(prompt)

        combined = "\n\n".join(summaries)
        abstract_clause = f"\n摘要供参考: {abstract}" if abstract else ""
        prompt = textwrap.dedent(
            f"""
            你是一位科研助理。以下是对论文不同部分的提炼笔记，请整合它们，
            用{self._settings.summary_language}输出{self._settings.summary_sentence_count}条要点，
            每条阐述一个核心发现或贡献，并说明对应的证据或方法。
            标题: {title}
            局部总结: {combined}{abstract_clause}
            """
        ).strip()
        return await self._call_llm(prompt)

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

    def _chunk_text(self, text: str) -> List[str]:
        text = text.strip()
        if not text:
            return []
        chunk_size = max(1000, self._settings.full_text_chunk_chars)
        overlap = max(0, min(self._settings.full_text_chunk_overlap, chunk_size // 2))
        chunks: List[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(length, start + chunk_size)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= length:
                break
            start = end - overlap
        return chunks

    async def _call_llm(self, prompt: str) -> str:
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


def get_summarizer(settings_override: Optional[Settings] = None) -> Summarizer:
    return Summarizer(configuration=settings_override or settings)
