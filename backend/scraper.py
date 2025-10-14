from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, cast

import time

import feedparser
import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings

ARXIV_RSS_BASE = "https://export.arxiv.org/rss"


@dataclass(slots=True)
class ScrapedPaper:
    arxiv_id: str
    title: str
    authors: List[str]
    affiliations: List[Optional[str]]
    abstract: str
    categories: List[str]
    link: str
    pdf_url: str | None
    published_at: datetime
    updated_at: datetime


def _parse_datetime(entry: feedparser.FeedParserDict, fallback: datetime | None = None) -> datetime:
    struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if isinstance(struct_time, time.struct_time):
        return datetime.fromtimestamp(time.mktime(struct_time), tz=timezone.utc)
    return fallback or datetime.now(tz=timezone.utc)


def _parse_entry(entry: feedparser.FeedParserDict) -> ScrapedPaper:
    arxiv_id = entry.get("id") or entry.get("link")
    link = entry.get("link")
    pdf_url = None
    for link_entry in entry.get("links") or []:
        link_type = link_entry.get("type")
        href = link_entry.get("href")
        if link_type == "application/pdf" and isinstance(href, str):
            pdf_url = href
            break
    authors: List[str] = []
    affiliations: List[Optional[str]] = []
    for author in entry.get("authors") or []:
        name = author.get("name")
        if isinstance(name, str) and name.strip():
            authors.append(name.strip())
            affiliation = author.get("affiliation")
            if isinstance(affiliation, str) and affiliation.strip():
                affiliations.append(affiliation.strip())
            else:
                affiliations.append(None)
    categories = []
    for tag in entry.get("tags") or []:
        term = tag.get("term")
        if isinstance(term, str) and term.strip():
            categories.append(term.strip())
    summary_raw = entry.get("summary")
    abstract = summary_raw.strip() if isinstance(summary_raw, str) else ""
    published_at = _parse_datetime(entry)
    updated_at = _parse_datetime(entry, fallback=published_at)

    arxiv_identifier = entry.get("id") or entry.get("link") or ""
    if isinstance(arxiv_identifier, list):
        arxiv_identifier = arxiv_identifier[0]

    title_raw = entry.get("title", "Untitled")
    if isinstance(title_raw, list):
        title_raw = title_raw[0]

    return ScrapedPaper(
        arxiv_id=str(arxiv_identifier).split("/")[-1],
        title=str(title_raw).strip() or "Untitled",
        authors=authors,
        affiliations=affiliations or [None] * len(authors),
        abstract=abstract,
        categories=categories,
        link=str(link) if link else "",
        pdf_url=str(pdf_url) if isinstance(pdf_url, str) else None,
        published_at=published_at,
        updated_at=updated_at,
    )


async def fetch_category(
    category: str,
    *,
    max_results: int,
    client: httpx.AsyncClient,
) -> List[ScrapedPaper]:
    url = f"{ARXIV_RSS_BASE}/{category}"

    async for attempt in AsyncRetrying(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
        retry=retry_if_exception_type(httpx.HTTPError),
    ):
        with attempt:
            response = await client.get(url, timeout=settings.request_timeout_seconds)
            response.raise_for_status()
            parsed = feedparser.parse(response.text)
            entries = (parsed.get("entries") or [])[:max_results]
            return [_parse_entry(entry) for entry in entries]

    return []


async def fetch_all_categories(
    categories: Iterable[str],
    *,
    max_results: int,
) -> List[ScrapedPaper]:
    async with httpx.AsyncClient() as client:
        tasks = [fetch_category(category, max_results=max_results, client=client) for category in categories]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    papers: List[ScrapedPaper] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        papers.extend(cast(List[ScrapedPaper], result))
    deduped: dict[str, ScrapedPaper] = {paper.arxiv_id: paper for paper in papers}
    return sorted(deduped.values(), key=lambda paper: paper.published_at, reverse=True)
