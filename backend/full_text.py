from __future__ import annotations

import asyncio
from io import BytesIO
from typing import List

import httpx
from pypdf import PdfReader

from .config import Settings

ARXIV_PDF_BASE = "https://arxiv.org/pdf"


async def fetch_full_text(arxiv_id: str, pdf_url: str | None, settings: Settings) -> str:
    """Download the paper PDF and extract machine-readable text."""

    candidates = _build_candidate_urls(arxiv_id, pdf_url)
    pdf_bytes: bytes | None = None

    async with httpx.AsyncClient() as client:
        for url in candidates:
            try:
                response = await client.get(url, timeout=settings.request_timeout_seconds)
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                continue
            pdf_bytes = response.content
            if pdf_bytes:
                break

    if not pdf_bytes:
        return ""

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _pdf_bytes_to_text, pdf_bytes)


def _build_candidate_urls(arxiv_id: str, pdf_url: str | None) -> List[str]:
    urls: List[str] = []
    if pdf_url:
        urls.append(pdf_url)
        if not pdf_url.lower().endswith(".pdf"):
            urls.append(f"{pdf_url.rstrip('/')}.pdf")
    cleaned = arxiv_id.strip()
    if cleaned:
        urls.append(f"{ARXIV_PDF_BASE}/{cleaned}.pdf")
        if "v" in cleaned:
            base_id = cleaned.split("v", 1)[0]
            if base_id and base_id != cleaned:
                urls.append(f"{ARXIV_PDF_BASE}/{base_id}.pdf")
    # deduplicate while keeping order
    seen: set[str] = set()
    unique_urls: List[str] = []
    for url in urls:
        if url not in seen:
            unique_urls.append(url)
            seen.add(url)
    return unique_urls


def _pdf_bytes_to_text(payload: bytes) -> str:
    if not payload:
        return ""
    try:
        with BytesIO(payload) as buffer:
            reader = PdfReader(buffer)
            fragments: List[str] = []
            for page in reader.pages:
                extracted = page.extract_text() or ""
                fragments.append(extracted.strip())
    except Exception:
        return ""
    return "\n\n".join(fragment for fragment in fragments if fragment)
