"""
pytest 公共装置。

两条纪律从 v1 的冒烟脚本继承下来：
1. **绝不写真实库。** 每个测试用 tmp_path 下的一次性库，并且显式断言它不在 app/data 下面。
   手录的快照和内容画像没有第二个来源，测试碰坏了就没了。
2. **数据放插槽里。** 测试输入在 tests/fixtures/*.json，改数据不用动测试代码。
"""
import json
import os
import pathlib

import pytest

# 鉴权配置在 app.main 导入时读一次，所以必须在任何 app 导入之前设好。
# 测试统一走 Bearer token 这条通道：既让每个既有测试都真的过一遍鉴权，
# 又不用在每个 fixture 里模拟登录。口令那条通道由 test_auth.py 单独覆盖。
TEST_API_TOKEN = "test-token-not-a-secret"
os.environ.setdefault("SHIOME_API_TOKEN", TEST_API_TOKEN)
os.environ.setdefault("SHIOME_OWNER_ID", "local")

REPO = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REAL_DATA_DIR = (REPO / "app" / "data").resolve()


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def test_data() -> dict:
    return load_fixture("api_test_data.json")


@pytest.fixture
def vision_data() -> dict:
    return load_fixture("vision_confirmed.json")


@pytest.fixture
def csv_bytes() -> bytes:
    return (FIXTURES / "sample_import.csv").read_bytes()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """把整个 app 指向一次性测试库。"""
    from app import database

    path = (tmp_path / "shiome_test.db").resolve()
    assert REAL_DATA_DIR not in path.parents, f"拒绝在真实数据目录里跑测试：{path}"
    monkeypatch.setattr(database, "DB_PATH", path)
    database.init_db()
    return path


@pytest.fixture
def client(db_path):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, headers={"Authorization": f"Bearer {TEST_API_TOKEN}"}) as c:
        yield c


@pytest.fixture
def account_id(client) -> int:
    """全新库会自带一个空人设的默认账号；测试里给它填上人设。"""
    accounts = client.get("/api/accounts").json()
    assert accounts, "全新库应该自带一个默认账号"
    aid = accounts[0]["id"]
    client.patch(f"/api/accounts/{aid}", json={
        "display_name": "测试账号",
        "persona": "测试用人设：面向小众高意向人群，精准触达优先于泛量。",
        "goal_note": "高意向咨询数 > 粉丝数",
    })
    return aid


@pytest.fixture
def seeded(client, account_id, test_data):
    """按 fixture 数据建好异常期 + 作品 + 内容画像 + 快照，返回创建出来的 post id。"""
    for period in test_data["anomaly_periods"]:
        assert client.post("/api/anomaly-periods", json=period).status_code == 200

    post_ids = []
    for entry in test_data["posts"]:
        r = client.post("/api/posts", json={**entry["post"], "account_id": account_id})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        post_ids.append(pid)
        if entry.get("content_profile"):
            assert client.patch(f"/api/posts/{pid}/content-profile",
                                json=entry["content_profile"]).status_code == 200
        for snap in entry.get("snapshots", []):
            assert client.post(f"/api/posts/{pid}/snapshots", json=snap).status_code == 200
    return post_ids
