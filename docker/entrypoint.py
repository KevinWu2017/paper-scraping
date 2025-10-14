import os
import sys
import pwd
from pathlib import Path
from urllib.parse import urlparse

APP_ROOT = Path("/app")
DEFAULT_DB_URL = "sqlite:///./papers.sqlite3"


def _resolve_sqlite_path(url: str) -> Path | None:
    if not url or not url.startswith("sqlite:///"):
        return None

    parsed = urlparse(url)
    if parsed.scheme != "sqlite":
        return None

    if url.startswith("sqlite:////"):
        candidate = Path(parsed.path)
        return candidate

    relative_path = parsed.path.lstrip("/")
    if not relative_path:
        return None
    return (APP_ROOT / relative_path).resolve()


def _ensure_sqlite_permissions(path: Path, uid: int, gid: int) -> None:
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"[entrypoint] Unable to create directory {directory}", file=sys.stderr)

    try:
        os.chown(directory, uid, gid)
    except PermissionError:
        print(f"[entrypoint] Unable to chown directory {directory}", file=sys.stderr)

    if not path.exists():
        try:
            path.touch()
        except PermissionError:
            print(f"[entrypoint] Unable to create database file {path}", file=sys.stderr)

    if path.exists():
        try:
            os.chown(path, uid, gid)
        except PermissionError:
            print(f"[entrypoint] Unable to chown database file {path}", file=sys.stderr)


def _drop_privileges(username: str = "app") -> None:
    if os.geteuid() != 0:
        return

    try:
        user = pwd.getpwnam(username)
    except KeyError:
        print(f"[entrypoint] User '{username}' not found; continuing as root", file=sys.stderr)
        return

    db_url = os.environ.get("PAPER_DATABASE_URL", DEFAULT_DB_URL)
    db_path = _resolve_sqlite_path(db_url)
    if db_path is not None:
        _ensure_sqlite_permissions(db_path, user.pw_uid, user.pw_gid)

    os.setgroups([user.pw_gid])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    os.environ["HOME"] = user.pw_dir


def main() -> None:
    if len(sys.argv) <= 1:
        print("[entrypoint] No command provided", file=sys.stderr)
        sys.exit(1)

    _drop_privileges(os.environ.get("APP_USER", "app"))

    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
