"""Consistent SQLite snapshots; live databases must never be copied as ordinary files."""
import asyncio
import logging
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

logger = logging.getLogger("shiome.backups")


def snapshot(source: Path, destination: Path):
    """Write a verified snapshot to a new file, removing partial output on failure."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    fd, temp_name = tempfile.mkstemp(prefix=".shiome-backup-", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(temp_path)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("SQLite backup integrity check failed")
        # Publish only a complete database, atomically and without replacing another file.
        os.link(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)


async def daily_backups(interval_seconds: float = 3600):
    """Check hourly so servers that stay running also get one snapshot each day."""
    from app.database import backup_db

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            path = await asyncio.to_thread(backup_db)
            if path:
                logger.info("Daily snapshot created: %s", path.name)
        except Exception:
            logger.exception("Daily backup failed; retrying at the next hourly check")
