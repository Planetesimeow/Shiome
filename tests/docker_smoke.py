"""Disposable Compose deployment including HTTPS, secure cookies and disk persistence.

Run only in an isolated checkout: creates .env.production and binds localhost ports 80/443.
Uses a dedicated project and deletes only that project's test volumes on completion.
"""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import time
import urllib.error
import urllib.request

from app.auth import hash_password


def main():
    env_file = Path(".env.production")
    # Never overwrite a deployed instance's secrets, even if someone runs this by mistake.
    with env_file.open("x", encoding="utf-8") as file:
        file.write(f"SHIOME_PASSWORD_HASH={hash_password('docker-test-password')}\n"
                   f"SHIOME_SECRET_KEY={secrets.token_hex(32)}\nSHIOME_MONTHLY_BUDGET_USD=1\n")
    env = {**os.environ, "SHIOME_DOMAIN": "localhost"}
    command = ["docker", "compose", "--project-name", "shiome-ci-smoke", "--env-file", os.devnull,
               "-f", "compose.yaml", "-f", "deploy/compose.small.yaml"]
    # The local-only CA is intentionally untrusted on the ephemeral CI runner.
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request("https://localhost" + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            return opener.open(req, timeout=10)
        except urllib.error.HTTPError as response:
            return response

    try:
        subprocess.run(command + ["up", "--build", "--detach", "--wait", "--wait-timeout", "120"], env=env, check=True)
        for _ in range(30):
            try:
                if request("/healthz").status == 200:
                    break
            except urllib.error.URLError:
                pass
            time.sleep(1)
        assert request("/healthz").status == 200
        assert request("/api/accounts").status == 401
        login = request("/api/auth/login", {"password": "docker-test-password"})
        assert login.status == 200, "raw env_file must preserve scrypt's dollar signs"
        assert "Secure" in login.headers["Set-Cookie"]
        assert "no-store" in login.headers["Cache-Control"]
        # Only the test service's named volume should persist through replacement.
        created = json.load(request("/api/posts", {"title": "container persistence test", "publish_date": "2026-09-11", "plays": 123}))
        assert created["id"]
        subprocess.run(command + ["up", "--detach", "--force-recreate", "--wait", "app"], env=env, check=True)
        # Caddy may briefly retain a connection to the old app container.
        for _ in range(30):
            if request("/healthz").status == 200:
                break
            time.sleep(1)
        posts = json.load(request("/api/posts"))
        assert any(post["title"] == "container persistence test" for post in posts)
        backup = request("/api/backup").read()
        assert backup.startswith(b"SQLite format 3\x00")
        # Exercise real image decoding/resizing under the small-container memory limit.
        # This runs the local preparation code only, with a synthetic image and no API call.
        subprocess.run(command + ["exec", "-T", "app", "python", "-c",
            "import io; from PIL import Image; from app.vision import prepare_image; "
            "buf=io.BytesIO(); im=Image.new('RGB',(4000,3000),'white'); im.save(buf,format='PNG'); "
            "del im; mime,data=prepare_image(buf.getvalue()); assert mime=='image/jpeg' and data; "
            "print('PASS 12 MP image preparation under memory limit')"], env=env, check=True)
        print("PASS small Compose deployment: HTTPS, auth, literal secrets, persistence and backup")
    finally:
        subprocess.run(command + ["logs", "--tail", "30"], env=env)
        subprocess.run(command + ["down", "--volumes"], env=env)
        env_file.unlink()


if __name__ == "__main__":
    main()
