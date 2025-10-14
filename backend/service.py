from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings, settings
from .models import Paper
from .schemas import PaginatedPapers, PaperOut, RefreshResponse
from .scraper import ScrapedPaper, fetch_all_categories
from .summarizer import Summarizer, get_summarizer


@dataclass(slots=True)
class RefreshStats:
    fetched: int = 0
    created: int = 0
    summarized: int = 0

    def to_response(self) -> RefreshResponse:
        return RefreshResponse(fetched=self.fetched, created=self.created, summarized=self.summarized)


ProgressReporter = Callable[[int, int, RefreshStats, ScrapedPaper | None], None]


class PaperService:
    def __init__(
        self,
        session: Session,
        configuration: Settings | None = None,
        summarizer: Summarizer | None = None,
    ) -> None:
        self.session = session
        self.settings = configuration or settings
        self.summarizer = summarizer or get_summarizer(self.settings)

    async def refresh(
        self,
        *,
        categories: Iterable[str] | None = None,
        progress: ProgressReporter | None = None,
    ) -> RefreshStats:
        categories = list(categories or self.settings.arxiv_categories)
        scraped: List[ScrapedPaper] = await fetch_all_categories(
            categories,
            max_results=self.settings.max_results_per_category,
        )
        stats = RefreshStats(fetched=len(scraped))
        total = len(scraped)
        self._emit_progress(progress, 0, total, stats, None)
        for index, paper in enumerate(scraped, start=1):
            persisted = self._get_by_arxiv_id(paper.arxiv_id)
            if persisted:
                self._update_existing(persisted, paper)
                await self._summarize_if_needed(persisted, paper, stats)
            else:
                entity = Paper(
                    arxiv_id=paper.arxiv_id,
                    title=paper.title,
                    authors=";".join(paper.authors),
                    author_affiliations=";".join(
                        affiliation or "" for affiliation in getattr(paper, "affiliations", [])
                    )
                    if getattr(paper, "affiliations", None)
                    else None,
                    abstract=paper.abstract,
                    categories=",".join(paper.categories),
                    link=paper.link,
                    pdf_url=paper.pdf_url,
                    published_at=paper.published_at,
                    updated_at=paper.updated_at,
                )
                self.session.add(entity)
                await self._summarize_if_needed(entity, paper, stats)
                stats.created += 1
            self._emit_progress(progress, index, total, stats, paper)
        self.session.commit()
        return stats

    def list_papers(self, *, category: str | None, limit: int, offset: int = 0) -> PaginatedPapers:
        filters = []
        if category:
            filters.append(Paper.categories.like(f"%{category}%"))
        total = (
            self.session.scalar(select(func.count()).select_from(Paper).where(*filters))
            or 0
        )
        stmt = (
            select(Paper)
            .where(*filters)
            .order_by(Paper.published_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = [PaperOut.model_validate(paper) for paper in self.session.scalars(stmt)]
        return PaginatedPapers(items=items, total=total)

    def distinct_categories(self) -> List[str]:
        rows = self.session.execute(select(Paper.categories)).scalars().all()
        categories: set[str] = set()
        for row in rows:
            if not row:
                continue
            for item in row.split(","):
                if item.strip():
                    categories.add(item.strip())
        return sorted(categories)

    def _get_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
        return self.session.scalar(stmt)

    def _update_existing(self, entity: Paper, scraped: ScrapedPaper) -> None:
        entity.title = scraped.title  # type: ignore[assignment]
        entity.authors = ";".join(scraped.authors)  # type: ignore[assignment]
        if hasattr(scraped, "affiliations"):
            entity.author_affiliations = ";".join(  # type: ignore[assignment]
                affiliation or "" for affiliation in scraped.affiliations
            )
        entity.abstract = scraped.abstract  # type: ignore[assignment]
        entity.categories = ",".join(scraped.categories)  # type: ignore[assignment]
        entity.link = scraped.link  # type: ignore[assignment]
        entity.pdf_url = scraped.pdf_url  # type: ignore[assignment]
        entity.updated_at = scraped.updated_at  # type: ignore[assignment]
        self.session.add(entity)

    async def _summarize_if_needed(self, entity: Paper, paper: ScrapedPaper, stats: RefreshStats) -> None:
        existing_summary = (entity.summary or "").strip()
        if existing_summary:
            return
        if not paper.abstract:
            return
        if not self.summarizer.uses_llm:
            entity.summary = None  # type: ignore[assignment]
            entity.summary_model = "not-run"  # type: ignore[assignment]
            entity.summary_language = None  # type: ignore[assignment]
            entity.last_summarized_at = None  # type: ignore[assignment]
            self.session.add(entity)
            return
        try:
            summary_text = await self.summarizer.summarize(paper.title, paper.abstract)
        except Exception:
            summary_text = ""
        if summary_text:
            entity.mark_summarized(
                summary_text,
                model=self.settings.llm_model,
                language=self.settings.summary_language,
            )
            stats.summarized += 1
        else:
            entity.summary = None  # type: ignore[assignment]
            entity.summary_model = "llm-failed"  # type: ignore[assignment]
            entity.summary_language = None  # type: ignore[assignment]
            entity.last_summarized_at = None  # type: ignore[assignment]
        self.session.add(entity)

    @staticmethod
    def _emit_progress(
        reporter: ProgressReporter | None,
        current: int,
        total: int,
        stats: RefreshStats,
        paper: ScrapedPaper | None,
    ) -> None:
        if reporter is None:
            return
        try:
            reporter(current, total, stats, paper)
        except Exception:
            pass
