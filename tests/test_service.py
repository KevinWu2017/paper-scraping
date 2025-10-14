from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import pytest

from backend import database
from backend.config import Settings
from backend.models import Paper
from backend.scraper import ScrapedPaper
from backend.service import PaperService
from backend.summarizer import Summarizer


class DummySummarizer(Summarizer):
    def __init__(self) -> None:
        super().__init__(configuration=Settings(llm_api_key=None, scheduler_enabled=False))

    @property
    def uses_llm(self) -> bool:  # type: ignore[override]
        return False

    async def summarize(self, title: str, abstract: str, *, full_text: str | None = None) -> str:  # type: ignore[override]
        return f"摘要：{title}"


class CapturingSummarizer(Summarizer):
    def __init__(self) -> None:
        super().__init__(configuration=Settings(llm_api_key="fake", scheduler_enabled=False))
        self.calls: list[str | None] = []

    @property
    def uses_llm(self) -> bool:  # type: ignore[override]
        return True

    async def summarize(
        self,
        title: str,
        abstract: str,
        *,
        full_text: str | None = None,
    ) -> str:  # type: ignore[override]
        self.calls.append(full_text)
        return "FULL SUMMARY"


@pytest.fixture(autouse=True)
def in_memory_db() -> None:
    database.configure_engine("sqlite+pysqlite:///:memory:?cache=shared")
    database.init_db()


@pytest.mark.asyncio
async def test_refresh_persists_new_paper(monkeypatch) -> None:
    scraped = ScrapedPaper(
        arxiv_id="2401.00003v1",
        title="Test Paper",
        authors=["Alice", "Bob"],
        affiliations=["Example University", None],
        abstract="Abstract content",
        categories=["cs.DC"],
        link="https://arxiv.org/abs/2401.00003",
        pdf_url="https://arxiv.org/pdf/2401.00003",
        published_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
    )

    async def fake_fetch_all(categories, max_results):
        return [scraped]

    monkeypatch.setattr("backend.service.fetch_all_categories", fake_fetch_all)

    session = database.create_session()
    try:
        service = PaperService(
            session=session,
            configuration=Settings(llm_api_key=None, scheduler_enabled=False),
            summarizer=DummySummarizer(),
        )
        stats = await service.refresh()
        assert stats.created == 1
        saved = session.query(Paper).first()
        assert saved is not None
        saved = cast(Paper, saved)
        title_value = cast(str, saved.title)
        assert title_value == "Test Paper"
        affiliations_value = cast(str | None, saved.author_affiliations)
        assert (affiliations_value or "").split(";")[0] == "Example University"
        summary_value = cast(str | None, saved.summary)
        assert summary_value is None
        summary_model_value = cast(str | None, saved.summary_model)
        assert summary_model_value == "not-run"
        assert stats.summarized == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_refresh_fetches_full_text_for_llm(monkeypatch) -> None:
    scraped = ScrapedPaper(
        arxiv_id="2401.00003v2",
        title="Test Paper",
        authors=["Alice", "Bob"],
        affiliations=[None, None],
        abstract="Abstract content",
        categories=["cs.DC"],
        link="https://arxiv.org/abs/2401.00003",
        pdf_url="https://arxiv.org/pdf/2401.00003v2.pdf",
        published_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
    )

    async def fake_fetch_all(categories, max_results):
        return [scraped]

    async def fake_fetch_full_text(arxiv_id, pdf_url, settings):
        assert arxiv_id == scraped.arxiv_id
        return "完整全文"

    monkeypatch.setattr("backend.service.fetch_all_categories", fake_fetch_all)
    monkeypatch.setattr("backend.service.fetch_full_text", fake_fetch_full_text)

    session = database.create_session()
    summarizer = CapturingSummarizer()
    try:
        service = PaperService(
            session=session,
            configuration=Settings(llm_api_key="dummy", scheduler_enabled=False),
            summarizer=summarizer,
        )
        stats = await service.refresh()
        saved = session.query(Paper).first()
        assert saved is not None
        saved = cast(Paper, saved)
        summary_value = cast(str | None, saved.summary)
        assert summary_value == "FULL SUMMARY"
        assert stats.summarized == 1
        assert summarizer.calls == ["完整全文"]
    finally:
        session.close()
