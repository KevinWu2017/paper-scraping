from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from backend.scraper import ARXIV_RSS_BASE, fetch_category

SAMPLE_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<rss version="2.0">
  <channel>
    <title>arXiv cs.DC recent submissions</title>
    <item>
      <title>Paper One</title>
      <link>https://arxiv.org/abs/2401.00001</link>
      <guid isPermaLink="false">https://arxiv.org/abs/2401.00001v1</guid>
      <description>First abstract.</description>
      <author>Doe, John</author>
      <category domain="http://arxiv.org">cs.DC</category>
      <category domain="http://arxiv.org">cs.OS</category>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Paper Two</title>
      <link>https://arxiv.org/abs/2401.00002</link>
      <guid isPermaLink="false">https://arxiv.org/abs/2401.00002v1</guid>
      <description>Second abstract.</description>
      <author>Smith, Alice</author>
      <category domain="http://arxiv.org">cs.DC</category>
      <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_category_parses_feed() -> None:
    route = respx.get(f"{ARXIV_RSS_BASE}/cs.DC").mock(return_value=Response(200, text=SAMPLE_FEED))

    async with httpx.AsyncClient() as client:
        papers = await fetch_category("cs.DC", max_results=5, client=client)

    assert route.called
    assert len(papers) == 2
    first = papers[0]
    assert first.arxiv_id.endswith("00001v1") or first.arxiv_id.endswith("00001")
    assert "cs.DC" in first.categories
    assert first.abstract
    assert first.published_at.tzinfo is not None
    assert first.affiliations == [None]  # no affiliation data in sample feed