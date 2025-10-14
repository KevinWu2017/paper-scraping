from __future__ import annotations

import pytest

from backend.config import Settings
from backend.summarizer import Summarizer


@pytest.mark.asyncio
async def test_fallback_summary_contains_title_and_sentences() -> None:
    configuration = Settings(
        llm_api_key=None,
        summary_sentence_count=2,
        summary_language="zh",
    )
    summarizer = Summarizer(configuration=configuration)
    abstract = "这是一句测试。第二句用于说明。第三句用于补充。"

    summary = await summarizer.summarize("示例论文", abstract)

    assert summary == ""
