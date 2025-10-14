#!/usr/bin/env python
"""Utility script to pre-create the SQLite database file used by the app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

# Ensure we can import the backend package when run as a standalone script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import database
from backend.config import Settings


def _describe_sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "sqlite":
        return None
    if url.startswith("sqlite:////"):
        return Path(parsed.path)
    relative_path = parsed.path.lstrip("/")
    if not relative_path:
        return None
    return Path(relative_path).resolve()


def prepare_database(url_override: str | None = None) -> Path | None:
    settings = Settings()
    database_url = url_override or settings.database_url

    # Reconfigure engine to ensure we hit the same target as runtime.
    database.configure_engine(database_url)
    database.init_db()

    return _describe_sqlite_path(database_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the SQLite database file if it is missing.")
    parser.add_argument(
        "--database-url",
        dest="database_url",
        default=None,
        help="Override the DATABASE URL (defaults to PAPER_DATABASE_URL / config value)",
    )
    args = parser.parse_args(argv)

    path = prepare_database(args.database_url)
    if path:
        print(f"[init_sqlite] database ready at {path}")
    else:
        print("[init_sqlite] database initialised (non-sqlite backend)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
