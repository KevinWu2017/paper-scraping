from __future__ import annotations

import argparse
import asyncio
from typing import Sequence

from .database import create_session, init_db
from .service import PaperService


async def refresh_once(categories: Sequence[str] | None = None) -> None:
    session = create_session()
    try:
        service = PaperService(session=session)
        header_printed = False

        def report_progress(current: int, total: int, stats, paper) -> None:
            nonlocal header_printed
            if not header_printed:
                if total:
                    print(f"Fetched {stats.fetched} papers. Processing...", flush=True)
                else:
                    print("Fetched 0 papers. Nothing to process.", flush=True)
                header_printed = True
            if paper is None:
                return
            title = paper.title.replace("\n", " ").strip()
            if len(title) > 80:
                title = f"{title[:77]}..."
            print(
                f"[{current}/{total}] created={stats.created} summarized={stats.summarized} • {title}",
                flush=True,
            )

        stats = await service.refresh(categories=categories, progress=report_progress)
    finally:
        session.close()
    print(
        f"Fetched: {stats.fetched}, created: {stats.created}, summarized: {stats.summarized}",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArXiv paper toolkit")
    subparsers = parser.add_subparsers(dest="command")

    refresh = subparsers.add_parser("refresh", help="Fetch latest papers and summarize")
    refresh.add_argument(
        "--category",
        "-c",
        action="append",
        dest="categories",
        help="Limit refresh to specific arXiv categories",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return

    init_db()
    if args.command == "refresh":
        asyncio.run(refresh_once(categories=args.categories))


if __name__ == "__main__":
    main()
