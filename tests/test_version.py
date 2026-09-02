"""
版本号只有一个来源，但它出现在两个地方：app/__init__.py 和 CHANGELOG.md。
这个测试盯着两处一致 —— 版本号的意义就是「跑的到底是哪一版」，
一旦两处对不上，它就不再是个可信的答案了。规则见 docs/workflow.md。
"""
import pathlib
import re

import app

REPO = pathlib.Path(__file__).resolve().parents[1]
CHANGELOG = REPO / "CHANGELOG.md"

# 形如 0.3.0 或 0.3.0-dev.2
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-dev\.\d+)?$")


def _newest_released_heading() -> str:
    """CHANGELOG 里第一个带版本号的标题（跳过 Unreleased / 未发布）。"""
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^### \[(\d[^\]]*)\]", line)
        if m:
            return m.group(1)
    raise AssertionError("CHANGELOG.md 里没有找到任何版本标题")


def test_version_is_well_formed():
    assert VERSION_RE.match(app.__version__), (
        f"__version__ = {app.__version__!r} 不符合 docs/workflow.md 的格式")


def test_version_matches_changelog():
    assert app.__version__ == _newest_released_heading(), (
        "app/__init__.py 的 __version__ 和 CHANGELOG.md 最新的版本标题对不上。"
        "每个 PR 都要同时改这两处 —— 见 docs/workflow.md。")


def test_api_reports_the_same_version(client):
    assert client.get("/api/version").json()["version"] == app.__version__
