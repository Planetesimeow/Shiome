"""
花销统计与每月预算上限。

这块要守住的性质只有两条，但都很硬：
1. 认不出价格的调用不能被当成 0 元 —— 那会让账本看起来比实际便宜。
2. 超预算要在**发起调用之前**被挡住 —— 事后发现，钱已经花掉了。
"""
import pytest

from app.pricing import cost_usd, price_for
from app.usage import budget_blocked, month_key, month_spend, record_usage


# ---------- 价目 ----------

def test_known_models_are_priced():
    assert price_for("claude-haiku-4-5") == (1.00, 5.00)
    assert price_for("claude-opus-5") == (5.00, 25.00)


def test_dated_model_ids_fall_back_to_the_base_model():
    """项目里配的是 claude-haiku-4-5-20251001 这种带日期后缀的 ID。"""
    assert price_for("claude-haiku-4-5-20251001") == price_for("claude-haiku-4-5")


def test_unknown_model_is_none_not_a_guess():
    """编一个成本数字比没有数字更糟 —— 它看起来像是可信的。"""
    assert price_for("some-other-vendor-model") is None
    assert cost_usd("some-other-vendor-model", 1000, 1000) is None


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("SHIOME_PRICE_CLAUDE_HAIKU_4_5", "2,8")
    assert price_for("claude-haiku-4-5") == (2.0, 8.0)


def test_cost_arithmetic():
    # 100 万输入 @ $1 + 20 万输出 @ $5 = 1 + 1 = $2
    assert cost_usd("claude-haiku-4-5", 1_000_000, 200_000) == pytest.approx(2.0)


# ---------- 账本 ----------

@pytest.fixture
def conn(db_path):
    from app.database import get_conn
    with get_conn() as c:
        yield c


def test_usage_is_recorded_and_summed(conn):
    record_usage(conn, "anthropic", "claude-haiku-4-5", "analysis", 1_000_000, 200_000)
    record_usage(conn, "anthropic", "claude-haiku-4-5", "vision_extract", 1_000_000, 0)
    s = month_spend(conn)
    assert s["calls"] == 2
    assert s["spent_usd"] == pytest.approx(3.0)
    assert s["input_tokens"] == 2_000_000


def test_unpriced_calls_are_counted_separately(conn):
    """Gemini 那条路我们没有价目表 —— 要如实说'有几次没算进钱里'。"""
    record_usage(conn, "gemini", "gemini-3.5-flash", "vision_extract", 5000, 500)
    s = month_spend(conn)
    assert s["calls"] == 1 and s["unpriced_calls"] == 1
    assert s["spent_usd"] == 0, "算不出价的调用不能凭空变成金额"


def test_spend_is_scoped_to_the_month(conn):
    record_usage(conn, "anthropic", "claude-haiku-4-5", "analysis", 1_000_000, 0)
    assert month_spend(conn, month="1999-01")["calls"] == 0
    assert month_spend(conn, month=month_key())["calls"] == 1


def test_by_model_breakdown(conn):
    record_usage(conn, "anthropic", "claude-opus-5", "analysis", 1_000_000, 0)
    record_usage(conn, "anthropic", "claude-haiku-4-5", "analysis", 1_000_000, 0)
    models = [m["model"] for m in month_spend(conn)["by_model"]]
    assert models[0] == "claude-opus-5", "最贵的排最前面"


# ---------- 上限 ----------

def test_no_limit_by_default(conn, monkeypatch):
    monkeypatch.delenv("SHIOME_MONTHLY_BUDGET_USD", raising=False)
    record_usage(conn, "anthropic", "claude-opus-5", "analysis", 10_000_000, 0)
    s = month_spend(conn)
    assert s["limit_usd"] is None and not s["over_budget"]
    assert budget_blocked(conn) is None, "没设上限就不该拦"


def test_blocks_once_over_limit(conn, monkeypatch):
    monkeypatch.setenv("SHIOME_MONTHLY_BUDGET_USD", "1")
    record_usage(conn, "anthropic", "claude-opus-5", "analysis", 1_000_000, 0)  # $5
    blocked = budget_blocked(conn)
    assert blocked is not None
    assert not blocked["retryable"]
    assert "预算" in blocked["_api_error"]


def test_under_limit_passes(conn, monkeypatch):
    monkeypatch.setenv("SHIOME_MONTHLY_BUDGET_USD", "100")
    record_usage(conn, "anthropic", "claude-haiku-4-5", "analysis", 1_000_000, 0)  # $1
    assert budget_blocked(conn) is None
    assert month_spend(conn)["remaining_usd"] == pytest.approx(99.0)


@pytest.mark.parametrize("bad", ["", "not-a-number", "0", "-5"])
def test_malformed_limit_means_no_limit(conn, monkeypatch, bad):
    monkeypatch.setenv("SHIOME_MONTHLY_BUDGET_USD", bad)
    assert month_spend(conn)["limit_usd"] is None


# ---------- 端到端：闸门在花钱之前 ----------

def test_analysis_is_refused_when_over_budget(client, seeded, monkeypatch):
    monkeypatch.setenv("SHIOME_MONTHLY_BUDGET_USD", "0.01")
    from app.database import get_conn
    with get_conn() as c:
        record_usage(c, "anthropic", "claude-opus-5", "analysis", 1_000_000, 0)

    body = client.post(f"/api/analyze/posts/{seeded[0]}/enhancement").json()
    assert body.get("_api_error") and "预算" in body["_api_error"]
    assert body["_budget"]["over_budget"]


def test_vision_extract_is_refused_when_over_budget(client, monkeypatch):
    """截图提取很可能是花销大头，它必须一起被挡。"""
    monkeypatch.setenv("SHIOME_MONTHLY_BUDGET_USD", "0.01")
    from app.database import get_conn
    with get_conn() as c:
        record_usage(c, "anthropic", "claude-opus-5", "vision_extract", 1_000_000, 0)

    r = client.post("/api/vision/extract",
                    files={"file": ("x.png", b"not-really-a-png", "image/png")})
    assert r.json().get("_api_error"), "超预算时不该还去读图片"


def test_usage_endpoint(client):
    body = client.get("/api/usage").json()
    assert body["month"] == month_key()
    assert set(body) >= {"spent_usd", "limit_usd", "calls", "by_model"}


@pytest.mark.parametrize("credentials", ["cookie", "bearer"])
def test_auth_and_budget_gates_work_together(seeded, monkeypatch, credentials):
    """Both authentication channels must preserve the budget gate on every paid route."""
    from unittest.mock import Mock

    from fastapi.testclient import TestClient

    from app import main
    from app.auth import AuthConfig, hash_password
    from app.database import get_conn

    password = "budget-test-password"
    token = "budget-test-token"
    monkeypatch.setattr(main, "AUTH", AuthConfig(env={
        "SHIOME_PASSWORD_HASH": hash_password(password),
        "SHIOME_SECRET_KEY": "budget-test-secret",
        "SHIOME_API_TOKEN": token,
    }))
    monkeypatch.setenv("SHIOME_MONTHLY_BUDGET_USD", "1")

    post_call = Mock(return_value={"ok": True})
    account_call = Mock(return_value={"ok": True})
    vision_call = Mock(return_value={"ok": True})
    monkeypatch.setitem(main.ANALYSES["enhancement"], "run", post_call)
    monkeypatch.setitem(main.ANALYSES["content_ideas"], "run", account_call)
    monkeypatch.setattr(main, "extract_screenshot", vision_call)
    routes = [
        (f"/api/analyze/posts/{seeded[0]}/enhancement", {}, post_call),
        ("/api/analyze/account/content_ideas", {}, account_call),
        ("/api/vision/extract",
         {"files": {"file": ("x.png", b"mock-image", "image/png")}}, vision_call),
    ]

    with TestClient(main.app) as c:
        assert c.get("/api/usage").status_code == 401
        for route, options, call in routes:
            assert c.post(route, **options).status_code == 401
            call.assert_not_called()

        if credentials == "cookie":
            assert c.post("/api/auth/login", json={"password": password}).status_code == 200
        else:
            c.headers["Authorization"] = f"Bearer {token}"

        assert c.get("/api/usage").status_code == 200
        for route, options, call in routes:
            response = c.post(route, **options)
            assert response.status_code == 200
            assert response.json() == {"ok": True}
            call.assert_called_once()
            call.reset_mock()

        with get_conn() as conn:
            record_usage(conn, "anthropic", "claude-haiku-4-5", "analysis", 1_000_000, 0)

        usage = c.get("/api/usage")
        assert usage.status_code == 200
        assert usage.json()["over_budget"]
        for route, options, call in routes:
            response = c.post(route, **options)
            assert response.status_code == 200
            assert response.json()["_budget"]["over_budget"]
            assert response.json()["retryable"] is False
            call.assert_not_called()
