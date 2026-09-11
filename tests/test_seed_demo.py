"""Demo commands must never erase an existing database, even an empty one."""
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest


def seed(target=None):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("SHIOME_DB_PATH", None)
    if target is not None:
        env["SHIOME_DB_PATH"] = str(target)
    return subprocess.run([sys.executable, "-m", "scripts.seed_demo"],
                          cwd=Path(__file__).resolve().parents[1], env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_demo_requires_explicit_path():
    assert seed().returncode != 0


@pytest.mark.parametrize("content", [b"", b"valuable existing file"])
def test_demo_refuses_any_existing_file(tmp_path, content):
    target = tmp_path / "existing.db"
    target.write_bytes(content)
    assert seed(target).returncode != 0
    assert target.read_bytes() == content


def test_demo_creates_once_and_keeps_real_changes_on_rerun(tmp_path):
    target = tmp_path / "demo.db"
    result = seed(target)
    assert result.returncode == 0, result.stderr
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        conn.execute("UPDATE accounts SET goal_note='keep my edits'")
        conn.commit()
    before = target.read_bytes()
    assert seed(target).returncode != 0
    assert target.read_bytes() == before
