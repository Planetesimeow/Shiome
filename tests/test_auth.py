"""
鉴权。

测试覆盖口令、会话、限速及远程访问边界：
口令和会话本身的密码学部分、没配鉴权时的兜底行为、以及两条通道（cookie / Bearer）。
"""
import pytest
from fastapi.testclient import TestClient

from app.auth import (
    AuthConfig, LoginThrottle, SESSION_COOKIE, hash_password, is_loopback,
    make_session, read_session, verify_password,
)

PASSWORD = "correct-horse-battery"


# ---------- 口令 ----------

def test_password_roundtrip():
    stored = hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored)
    assert not verify_password("wrong", stored)


def test_same_password_hashes_differently():
    """每次都要有新盐，否则两个人用同样的口令一眼就能看出来。"""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


@pytest.mark.parametrize("garbage", ["", "notahash", "md5$aa$bb", None])
def test_malformed_hash_fails_closed(garbage):
    assert not verify_password(PASSWORD, garbage)


# ---------- 会话 ----------

def test_session_roundtrip():
    token = make_session("local", "sekrit")
    assert read_session(token, "sekrit")["sub"] == "local"


def test_session_rejects_tampering():
    token = make_session("local", "sekrit")
    payload, _, sig = token.partition(".")
    assert read_session(f"{payload}x.{sig}", "sekrit") is None      # 改了内容
    assert read_session(f"{payload}.{sig[:-2]}xy", "sekrit") is None  # 改了签名
    assert read_session(token, "different-secret") is None          # 换了密钥


def test_session_expires():
    assert read_session(make_session("local", "s", days=-1), "s") is None


@pytest.mark.parametrize("bad", [None, "", "nodot", "a.b.c"])
def test_session_garbage_is_none(bad):
    assert read_session(bad, "s") is None


# ---------- 配置 ----------

def test_unconfigured_when_nothing_set():
    assert not AuthConfig(env={}).configured


def test_secret_is_derived_but_stable():
    """没设 SHIOME_SECRET_KEY 时派生，但两次读出来必须一样 —— 否则重启就掉登录。"""
    env = {"SHIOME_PASSWORD_HASH": hash_password(PASSWORD)}
    a, b = AuthConfig(env=env), AuthConfig(env=env)
    assert a.secret_derived and a.secret == b.secret


def test_loopback_detection():
    assert is_loopback("127.0.0.1") and is_loopback("::1")
    assert not is_loopback("203.0.113.9") and not is_loopback(None)


# ---------- 限速 ----------

def test_throttle_blocks_after_limit():
    t = LoginThrottle(limit=3, window_sec=900)
    for _ in range(3):
        assert t.check("ip")
        t.record_failure("ip")
    assert not t.check("ip")


def test_successful_login_clears_throttle():
    t = LoginThrottle(limit=3)
    t.record_failure("ip")
    t.reset("ip")
    assert t.check("ip")


# ---------- 端到端 ----------

@pytest.fixture
def unauth_client(db_path, monkeypatch):
    """一个不带任何凭据的客户端，且服务端配了口令。"""
    from app import main
    monkeypatch.setattr(main, "AUTH", AuthConfig(env={
        "SHIOME_PASSWORD_HASH": hash_password(PASSWORD),
        "SHIOME_SECRET_KEY": "test-secret",
    }))
    monkeypatch.setattr(main, "THROTTLE", LoginThrottle())
    with TestClient(main.app) as c:
        yield c


def test_api_without_credentials_is_401(unauth_client):
    assert unauth_client.get("/api/posts").status_code == 401


def test_browser_without_credentials_is_redirected(unauth_client):
    r = unauth_client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_version_and_login_page_stay_public(unauth_client):
    assert unauth_client.get("/api/version").status_code == 200
    assert unauth_client.get("/login").status_code == 200
    assert unauth_client.get("/static/style.css").status_code == 200


def test_login_then_access(unauth_client):
    assert unauth_client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert unauth_client.cookies.get(SESSION_COOKIE)
    assert unauth_client.get("/api/posts").status_code == 200


def test_wrong_password_is_401(unauth_client):
    assert unauth_client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert unauth_client.get("/api/posts").status_code == 401


def test_login_is_rate_limited(unauth_client):
    codes = [unauth_client.post("/api/auth/login", json={"password": "nope"}).status_code
             for _ in range(12)]
    assert 429 in codes, "连续猜口令必须被挡下来"


def test_logout_revokes_the_session(unauth_client):
    unauth_client.post("/api/auth/login", json={"password": PASSWORD})
    unauth_client.post("/api/auth/logout")
    assert unauth_client.get("/api/posts").status_code == 401


def test_bearer_token_works(db_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "AUTH", AuthConfig(env={"SHIOME_API_TOKEN": "tok"}))
    with TestClient(main.app) as c:
        assert c.get("/api/posts").status_code == 401
        assert c.get("/api/posts", headers={"Authorization": "Bearer tok"}).status_code == 200
        assert c.get("/api/posts", headers={"Authorization": "Bearer wrong"}).status_code == 401


# ---------- 没配鉴权时的兜底 ----------
#
# 这两个测试要控制「请求来自哪个 IP」。TestClient 的 client= 参数是新版 starlette 才有的，
# requirements.txt 钉的版本没有它 —— 所以改成替换 _client_key（中间件读来源地址的那一个函数）。
# 取地址本身由下面的 test_client_key_reads_the_peer_address 单独盯着，覆盖没有变少。


class _FakePeer:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, host):
        self.client = _FakePeer(host) if host else None


def test_client_key_reads_the_peer_address():
    from app.main import _client_key
    assert _client_key(_FakeRequest("203.0.113.9")) == "203.0.113.9"
    assert _client_key(_FakeRequest(None)) == "unknown", "拿不到来源地址不能当成本机"


def test_unconfigured_allows_loopback(db_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "AUTH", AuthConfig(env={}))
    monkeypatch.setattr(main, "_client_key", lambda request: "127.0.0.1")
    with TestClient(main.app) as c:
        assert c.get("/api/posts").status_code == 200


def test_unconfigured_refuses_everything_else(db_path, monkeypatch):
    """
    没配鉴权就丢到公网 —— 这是这类小工具最常见的事故。默认必须是关着的。
    """
    from app import main
    monkeypatch.setattr(main, "AUTH", AuthConfig(env={}))
    monkeypatch.setattr(main, "_client_key", lambda request: "203.0.113.9")
    with TestClient(main.app) as c:
        r = c.get("/api/posts")
        assert r.status_code == 403
        assert "鉴权" in r.json()["detail"]
