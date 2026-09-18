"""Usage: python -m scripts.backup /path/to/new-snapshot.db"""
import argparse
from pathlib import Path

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="Export a consistent SQLite snapshot to a NEW file")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    load_dotenv()
    from app.database import DB_PATH
    from app.backups import snapshot
    snapshot(DB_PATH, args.destination)
    print(f"Verified snapshot saved: {args.destination}")


if __name__ == "__main__":
    main()
