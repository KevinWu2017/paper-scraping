from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

from .config import settings
from .database import create_session, get_session, init_db
from .schemas import PaginatedPapers, RefreshResponse
from .service import PaperService

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

app = FastAPI(title="ArXiv Paper Digest", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

logger = logging.getLogger(__name__)

_scheduler: Optional["AsyncIOScheduler"] = None
_initial_refresh_task: Optional[asyncio.Task[None]] = None


def get_service(session: Session = Depends(get_session)) -> PaperService:
    return PaperService(session=session)


@app.on_event("startup")
async def startup_event() -> None:
    global _scheduler, _initial_refresh_task
    init_db()

    if settings.scheduler_enabled:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        timezone = ZoneInfo(settings.scheduler_timezone)
        _scheduler = AsyncIOScheduler(timezone=timezone)
        _scheduler.add_job(
            scheduled_refresh_job,
            "cron",
            hour=settings.refresh_hour,
            minute=settings.refresh_minute,
            id="refresh-arxiv",
            replace_existing=True,
        )
        _scheduler.start()

    async def _run_initial_refresh() -> None:
        try:
            await scheduled_refresh_job()
            logger.info("Initial refresh completed")
        except Exception:  # pragma: no cover - logged for observability
            logger.exception("Initial refresh failed")

    _initial_refresh_task = asyncio.create_task(_run_initial_refresh())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _scheduler, _initial_refresh_task
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _initial_refresh_task and not _initial_refresh_task.done():
        _initial_refresh_task.cancel()
    _initial_refresh_task = None


async def scheduled_refresh_job() -> None:
    session = create_session()
    try:
        service = PaperService(session=session)
        await service.refresh()
    finally:
        session.close()


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/papers", response_model=PaginatedPapers)
async def list_papers(
    category: str | None = Query(default=None, description="Filter by arXiv category code"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: PaperService = Depends(get_service),
) -> PaginatedPapers:
    return service.list_papers(category=category, limit=limit, offset=offset)


@app.get("/api/categories")
async def categories(service: PaperService = Depends(get_service)) -> list[str]:
    categories = service.distinct_categories()
    return categories or list(settings.arxiv_categories)


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh_endpoint(
    service: PaperService = Depends(get_service),
    x_admin_token: str | None = Header(default=None, convert_underscores=False),
) -> RefreshResponse:
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    stats = await service.refresh()
    return stats.to_response()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, service: PaperService = Depends(get_service)) -> HTMLResponse:
    categories = service.distinct_categories() or settings.arxiv_categories
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": categories,
            "default_category": categories[0] if categories else None,
        },
    )
