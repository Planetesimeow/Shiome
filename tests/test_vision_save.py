"""
截图确认入库。提取本身要调模型（见 test_analysis.py），这里只测确认之后的落库路径。
"""


def test_detail_page_creates_post_and_snapshot(client, account_id, vision_data):
    r = client.post("/api/vision/save", json=vision_data["detail"]).json()
    assert r["inserted"] + r["updated"] == 1
    assert r["snapshots"] == 1

    post = next(p for p in client.get("/api/posts").json()
                if p["title"] == vision_data["detail"]["videos"][0]["title"])
    assert post["bounce_2s_rate"] == 0.2716
    assert post["cover_ctr"] == 0.621


def test_detail_snapshot_carries_the_curve_observation(client, account_id, vision_data):
    """详情页的小时级趋势图是定性读的，作为数字快照的旁证喂给扩散诊断。"""
    client.post("/api/vision/save", json=vision_data["detail"])
    post = client.get("/api/posts").json()[0]
    vision_snaps = [s for s in client.get(f"/api/posts/{post['id']}/snapshots").json()
                    if s["source"] == "vision"]
    assert len(vision_snaps) == 1
    assert "健康爬升" in (vision_snaps[0]["curve_note"] or "")


def test_private_videos_are_refused(client, account_id, vision_data):
    """私密作品别人看不到，数据不作数 —— 服务端拒绝入库，不靠前端自觉。"""
    r = client.post("/api/vision/save", json=vision_data["list"]).json()
    assert r["skipped_private"] == 1
    titles = [p["title"] for p in client.get("/api/posts").json()]
    assert "冒烟·私密视频E" not in titles


def test_account_page_lands_in_account_metrics(client, account_id, vision_data):
    r = client.post("/api/vision/save", json=vision_data["account"]).json()
    assert r["account_saved"]
    metrics = client.get("/api/account-metrics").json()
    assert metrics and metrics[0]["search_views"] == 652
    assert metrics[0]["account_id"] == account_id


def test_vision_never_touches_hand_entered_content_profile(client, account_id, vision_data):
    """
    v2 之后这在结构上就不可能了 —— 内容画像根本不在 posts 表上。
    留着这个测试是为了把这条规矩钉住：数据同步路径不许碰手填的内容。
    """
    detail = vision_data["detail"]
    client.post("/api/vision/save", json=detail)
    post = client.get("/api/posts").json()[0]
    profile = {"hook_description": "手填的钩子描述", "content_pillar": "体态反差"}
    client.patch(f"/api/posts/{post['id']}/content-profile", json=profile)

    client.post("/api/vision/save", json=detail)   # 再同步一次数字
    again = client.get(f"/api/posts/{post['id']}").json()
    assert again["creative"]["hook_description"] == "手填的钩子描述"
    assert again["creative"]["content_pillar"] == "体态反差"
