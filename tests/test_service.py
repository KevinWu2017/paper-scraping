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

    async def summarize(self, title: str, abstract: str) -> str:  # type: ignore[override]
        return f"摘要：{title}"


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
        assert saved.title == "Test Paper"
        assert (saved.author_affiliations or "").split(";")[0] == "Example University"
        assert saved.summary is None
        assert saved.summary_model == "not-run"
        assert stats.summarized == 0
    finally:
        session.close()
