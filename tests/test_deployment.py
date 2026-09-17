"""Public deployment must fail closed, keep data, and produce restorable backups."""
import asyncio
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthConfig, hash_password
from app.backups import daily_backups, snapshot
from scripts.restore import restore


@pytest.mark.parametrize("env", [
    {}, {"SHIOME_API_TOKEN": "script-only"},
    {"SHIOME_PASSWORD_HASH": "scrypt$broken$broken", "SHIOME_SECRET_KEY": "x" * 64},
    {"SHIOME_PASSWORD_HASH": hash_password("test-password")},
    {"SHIOME_PASSWORD_HASH": hash_password("test-password"), "SHIOME_SECRET_KEY": "short"},
])
def test_production_refuses_missing_browser_credentials(db_path, monkeypatch, env):
    import app.main as main
    monkeypatch.setattr(main, "AUTH", AuthConfig({"SHIOME_ENV": "production", **env}))
    with pytest.raises(RuntimeError, match="Production requires"):
        with TestClient(main.app):
            pass


def test_production_login_health_and_private_cache(db_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "AUTH", AuthConfig({
        "SHIOME_ENV": "production", "SHIOME_PASSWORD_HASH": hash_password("test-password"),
        "SHIOME_SECRET_KEY": "x" * 64,
    }))
    with TestClient(main.app, base_url="https://shiome.example") as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        anonymous = client.get("/api/backup")
        assert anonymous.status_code == 401
        assert anonymous.headers["cache-control"] == "no-store"
        response = client.post("/api/auth/login", json={"password": "test-password"})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
        for path in ["/", "/api/accounts", "/api/backup"]:
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
        client.post("/api/auth/logout")
        assert client.get("/api/accounts").status_code == 401


def test_download_restores_actual_data(seeded, client, db_path, tmp_path):
    response = client.get("/api/backup")
    assert response.status_code == 200
    exported = tmp_path / "export.db"
    exported.write_bytes(response.content)
    target = tmp_path / "restored.db"
    restore(exported, target)
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == len(seeded)
    with pytest.raises(FileExistsError):
        restore(exported, target)
    assert db_path.read_bytes() != b""


def test_failed_snapshot_does_not_leave_partial_backup(tmp_path):
    destination = tmp_path / "failed.db"
    with pytest.raises(sqlite3.Error):
        snapshot(tmp_path / "missing.db", destination)
    assert not destination.exists()


def test_live_service_retries_daily_backup(monkeypatch):
    from app import database
    calls = []

    def backup():
        calls.append(True)
        if len(calls) == 1:
            raise OSError("temporary storage failure")

    monkeypatch.setattr(database, "backup_db", backup)

    async def run():
        task = asyncio.create_task(daily_backups(0.01))
        try:
            for _ in range(200):
                if len(calls) >= 2:
                    break
                await asyncio.sleep(0.01)
            assert len(calls) >= 2
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(run())


def test_health_does_not_recreate_missing_database(client, monkeypatch, tmp_path):
    from app import database
    missing = tmp_path / "absent.db"
    monkeypatch.setattr(database, "DB_PATH", missing)
    assert client.get("/healthz").status_code == 503
    assert not missing.exists()


def test_large_image_rejected_before_model_call(client, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "extract_screenshot", lambda *args: pytest.fail("No paid call allowed"))
    response = client.post("/api/vision/extract", files={"file": ("large.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")})
    assert response.status_code == 413
