"""账号 / 作品 / 创作物 / 快照 / 异常期 的基本读写。"""


def test_default_account_exists_with_empty_persona(client):
    """全新库自带一个账号，但**不带人设** —— 不给新用户塞上别人的定位。"""
    accounts = client.get("/api/accounts").json()
    assert len(accounts) == 1
    assert accounts[0]["platform"] == "douyin"
    assert not accounts[0]["persona"]


def test_account_patch_roundtrip(client, account_id):
    a = client.get("/api/accounts").json()[0]
    assert a["display_name"] == "测试账号"
    assert "精准触达" in a["persona"]


def test_create_and_read_post(client, account_id, test_data):
    payload = {**test_data["posts"][0]["post"], "account_id": account_id}
    pid = client.post("/api/posts", json=payload).json()["id"]
    post = client.get(f"/api/posts/{pid}").json()
    assert post["title"] == payload["title"]
    assert post["platform"] == "douyin"
    assert post["account_id"] == account_id


def test_content_profile_creates_and_links_a_creative(client, account_id, test_data):
    """内容画像写的是 creative，不是 post —— 一条内容发多平台只填一次。"""
    pid = client.post("/api/posts", json={**test_data["posts"][0]["post"],
                                          "account_id": account_id}).json()["id"]
    assert client.get(f"/api/posts/{pid}").json()["creative_id"] is None

    profile = test_data["posts"][0]["content_profile"]
    creative = client.patch(f"/api/posts/{pid}/content-profile", json=profile).json()
    assert creative["hook_description"] == profile["hook_description"]

    post = client.get(f"/api/posts/{pid}").json()
    assert post["creative_id"] == creative["id"]
    assert post["creative"]["content_pillar"] == profile["content_pillar"]


def test_second_post_can_reuse_one_creative(client, account_id, test_data):
    """同一个 creative 挂两条 post：这就是多平台只描述一次的机制。"""
    base = test_data["posts"][0]["post"]
    p1 = client.post("/api/posts", json={**base, "account_id": account_id}).json()["id"]
    creative = client.patch(f"/api/posts/{p1}/content-profile",
                            json=test_data["posts"][0]["content_profile"]).json()

    p2 = client.post("/api/posts", json={
        **base, "title": base["title"] + "（另一个平台）", "platform_post_id": "OTHER-1",
        "account_id": account_id, "creative_id": creative["id"],
    }).json()["id"]

    assert client.get(f"/api/posts/{p2}").json()["creative"]["hook_description"] \
        == creative["hook_description"]


def test_snapshots_roundtrip(client, seeded):
    snaps = client.get(f"/api/posts/{seeded[0]}/snapshots").json()
    assert len(snaps) == 3
    assert snaps[0]["plays"] < snaps[-1]["plays"], "快照应按时间升序返回"


def test_anomaly_period_flags_posts(client, seeded):
    posts = client.get("/api/posts").json()
    assert sum(1 for p in posts if p["is_anomaly_period"]) >= 1


def test_baseline_excludes_anomaly_posts(client, seeded):
    baseline = client.get("/api/baseline").json()
    total = len(client.get("/api/posts").json())
    assert baseline["n"] < total, "基线应排除异常期作品"
    assert baseline["avg_completion_rate"] is not None


def test_delete_post_cascades(client, seeded):
    pid = seeded[0]
    r = client.delete(f"/api/posts/{pid}").json()
    assert r["snapshots_removed"] == 3
    assert client.get(f"/api/posts/{pid}").status_code == 404
    assert client.get(f"/api/posts/{pid}/snapshots").json() == []


def test_delete_missing_post_404(client):
    assert client.delete("/api/posts/99999").status_code == 404


def test_deleting_a_post_keeps_the_creative(client, account_id, test_data):
    """creative 可能还发在别的平台上，删一条 post 不该带走它。"""
    pid = client.post("/api/posts", json={**test_data["posts"][0]["post"],
                                          "account_id": account_id}).json()["id"]
    cid = client.patch(f"/api/posts/{pid}/content-profile",
                       json=test_data["posts"][0]["content_profile"]).json()["id"]
    client.delete(f"/api/posts/{pid}")
    assert client.get(f"/api/creatives/{cid}").status_code == 200


def test_trend_and_report_render(client, seeded):
    assert len(client.get("/api/trend-data").json()) == len(seeded)
    rep = client.get("/api/report")
    assert rep.status_code == 200
    assert "潮目 · 账号分析报告" in rep.text


def test_report_is_self_contained(client, seeded):
    """报告是要存档的东西：断网、几年后打开，图还得在。"""
    rep = client.get("/api/report").text
    assert "cdnjs" not in rep and "<script src=" not in rep
    assert "Chart" in rep


def test_report_download_header(client, seeded):
    r = client.get("/api/report?download=1")
    assert "attachment" in r.headers.get("content-disposition", "")


def test_analyses_registry_listed(client):
    names = {a["name"] for a in client.get("/api/analyses").json()}
    assert names == {"enhancement", "trend_forecast", "pool_diagnosis",
                     "content_ideas", "creator_profile"}


def test_creator_notes_roundtrip(client, account_id):
    """创作者写下的想法 —— 助手要懂你，光有数字不够。"""
    client.post("/api/creator-notes", json={"body": "想往买车避坑方向转", "account_id": account_id})
    notes = client.get("/api/creator-notes").json()
    assert notes and notes[0]["body"] == "想往买车避坑方向转"
