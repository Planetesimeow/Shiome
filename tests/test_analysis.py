"""
分析类端点 —— 会真的调 Anthropic API，要 key、要花钱。

默认**跳过**，而且是双保险：既有 marker（-m "not costs_money"），也有环境变量开关。
CI 和日常 pytest 都不会误花钱。要跑：

    SHIOME_TEST_WITH_ANALYSIS=1 pytest -m costs_money
"""
import os

import pytest


RUN = os.environ.get("SHIOME_TEST_WITH_ANALYSIS") and os.environ.get("ANTHROPIC_API_KEY")
needs_key = pytest.mark.skipif(
    not RUN, reason="要花钱：设 SHIOME_TEST_WITH_ANALYSIS=1 和 ANTHROPIC_API_KEY 才跑")


@pytest.mark.costs_money
@needs_key
@pytest.mark.parametrize("analysis", ["enhancement", "trend_forecast", "pool_diagnosis"])
def test_post_level_analyses(client, seeded, analysis):
    r = client.post(f"/api/analyze/posts/{seeded[0]}/{analysis}")
    assert r.status_code == 200
    body = r.json()
    assert not body.get("_parse_error"), body
    if body.get("_api_error"):
        pytest.skip(f"API 不可用：{body['_api_error']}")
    assert body.get("_meta", {}).get("input_tokens"), "成本要可见"


@pytest.mark.costs_money
@needs_key
@pytest.mark.parametrize("analysis", ["content_ideas", "creator_profile"])
def test_account_level_analyses(client, seeded, analysis):
    r = client.post(f"/api/analyze/account/{analysis}")
    assert r.status_code == 200
    assert not r.json().get("_parse_error"), r.text


@pytest.mark.costs_money
@needs_key
def test_results_are_cached_and_readable(client, seeded):
    client.post(f"/api/analyze/posts/{seeded[0]}/enhancement")
    cached = client.get(f"/api/analyze/results?post_id={seeded[0]}"
                        f"&analysis_type=enhancement").json()
    assert cached and cached[0]["model_used"]


def test_unknown_analysis_is_404_without_calling_the_api(client, seeded):
    """这个不花钱：路由层就该挡住，不该先调模型再发现名字不对。"""
    assert client.post(f"/api/analyze/posts/{seeded[0]}/nonsense").status_code == 404
    assert client.post("/api/analyze/account/nonsense").status_code == 404


def test_post_scope_and_account_scope_do_not_cross(client, seeded):
    """账号级分析不能从单条作品的路径调，反之亦然。"""
    assert client.post(f"/api/analyze/posts/{seeded[0]}/content_ideas").status_code == 404
    assert client.post("/api/analyze/account/enhancement").status_code == 404
