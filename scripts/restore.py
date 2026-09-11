"""Restore into a NEW path; switching SHIOME_DB_PATH is a separate, explicit step."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from app.backups import snapshot


def restore(source: Path, destination: Path):
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup is not a healthy SQLite database")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"accounts", "posts", "creatives", "post_snapshots"}.issubset(tables):
            raise ValueError("Backup is not a Shiome v2 database")
    snapshot(source, destination)


def main():
    parser = argparse.ArgumentParser(description="Restore a Shiome backup to a NEW database path")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    restore(args.source, args.destination)
    print(f"Restored: {args.destination}. Stop the app before changing SHIOME_DB_PATH to this file.")


if __name__ == "__main__":
    main()
