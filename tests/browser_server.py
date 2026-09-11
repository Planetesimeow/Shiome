"""Disposable browser-test server. Never imports API keys or uses a real database."""
import os
import tempfile
from pathlib import Path

temp = tempfile.TemporaryDirectory(prefix="shiome-browser-")
os.environ["SHIOME_DB_PATH"] = str(Path(temp.name) / "browser.db")
os.environ["SHIOME_ENV"] = "development"
os.environ["SHIOME_API_TOKEN"] = ""
os.environ["ANTHROPIC_API_KEY"] = "browser-tests-no-paid-calls"
os.environ["GEMINI_API_KEY"] = "browser-tests-no-paid-calls"

from app.auth import hash_password

os.environ["SHIOME_PASSWORD_HASH"] = hash_password("browser-test-password")
os.environ["SHIOME_SECRET_KEY"] = "browser-test-session-secret-only"

from app import main


def extract(*_args):
    return {
        "page_type": "video_detail",
        "videos": [{"title": '真实截图测试：稳定内容方向 "引号" 与手机长标题',
                    "status": "已发布", "publish_datetime": "2026-09-10 12:30:00",
                    "duration_sec": 18, "plays": 2388, "likes": 140,
                    "completion_rate": 0.36, "new_followers": 12}],
    }


main.extract_screenshot = extract

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=8765)
