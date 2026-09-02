"""
重复作品的发现与合并。

这是 v2 修掉的一个真实问题：线上库里有三组同一条视频的重复记录，因为 v1 按
(标题, 发布日期) 精确匹配，而列表页截图的标题是截断的、OCR 还会读错字。
"""
from app.dedupe import title_similarity, normalize_title

TRUNCATED = "六块腹肌的日本大厂程序员放松日吃了啥？又到我最爱的放松日啦～来一起看看今天都吃了些啥吧！#..."
FULL = ("六块腹肌的日本大厂程序员放纵日吃了啥？又到我最爱的放纵日啦~来一起看看今天都吃了些啥吧！"
        "#放纵日吃点啥 #上班族减脂 #程序员减脂 #薄肌养成")


def test_normalize_strips_truncation_marks():
    assert not normalize_title(TRUNCATED).endswith("...")


def test_truncated_and_full_titles_match_despite_ocr_drift():
    """放松/放纵 是 OCR 读错，不该让两条被当成不同的视频。"""
    assert title_similarity(TRUNCATED, FULL) >= 0.85


def test_unrelated_titles_do_not_match():
    assert title_similarity("同样1200大卡，差距居然这么明显！", "体脂12%程序员的减脂小技巧") < 0.85


def _make(client, account_id, **kw):
    body = {"title": "T", "publish_date": "2026-05-01", "account_id": account_id}
    body.update(kw)
    return client.post("/api/posts", json=body).json()["id"]


def test_upsert_matches_truncated_title_instead_of_duplicating(client, account_id, csv_bytes):
    """同一条作品先以完整标题入库，再以截断标题同步，应该更新而不是新建。"""
    _make(client, account_id, title=FULL, publish_date="2026-07-06", plays=5359)
    before = len(client.get("/api/posts").json())

    r = client.post("/api/vision/save", json={
        "page_type": "video_list",
        "videos": [{"status": "已发布", "title": TRUNCATED,
                    "publish_datetime": "2026-07-06", "plays": 5400}],
    }).json()
    assert r["updated"] == 1 and r["inserted"] == 0
    assert len(client.get("/api/posts").json()) == before


def test_candidates_flag_similar_titles(client, account_id):
    a = _make(client, account_id, title=TRUNCATED, publish_date="2026-07-06",
              plays=5355, likes=57, comments=7)
    b = _make(client, account_id, title=FULL, publish_date="2026-07-06",
              plays=5359, likes=57, comments=7, completion_rate=0.0129)
    groups = client.get("/api/posts/duplicate-candidates").json()
    assert len(groups) == 1
    assert set(groups[0]["post_ids"]) == {a, b}
    assert "标题高度相似" in groups[0]["reason"]


def test_candidates_flag_ocr_garbage_by_metric_fingerprint(client, account_id):
    """标题被读成乱码时，靠同日 + 点赞/评论完全相同兜住。"""
    a = _make(client, account_id, title="同样1200大卡，差距居然这么明显！...",
              publish_date="2026-07-05", plays=11000, likes=57, comments=37)
    b = _make(client, account_id, title="仙会3啖呃2", publish_date="2026-07-05",
              plays=10700, likes=57, comments=37, completion_rate=0.3324)
    groups = client.get("/api/posts/duplicate-candidates").json()
    assert set(groups[0]["post_ids"]) == {a, b}
    assert "OCR" in groups[0]["reason"]


def test_different_posts_same_day_are_not_flagged(client, account_id):
    _make(client, account_id, title="完全不同的选题一", publish_date="2026-05-02",
          plays=100, likes=5, comments=1)
    _make(client, account_id, title="另一个毫不相干的选题", publish_date="2026-05-02",
          plays=900, likes=44, comments=9)
    assert client.get("/api/posts/duplicate-candidates").json() == []


def test_merge_keeps_the_richer_row_and_the_longer_title(client, account_id):
    """
    合并规则要能解释给人听：底稿取字段最全的那条（详情页那份，数字更精确），
    标题取最长的那个（截断的信息少）。
    """
    rounded = _make(client, account_id, title="同样1200大卡，差距居然这么明显！你们对1200大卡有真实的概念吗...",
                    publish_date="2026-07-05", plays=11000, likes=57, comments=37)
    exact = _make(client, account_id, title="仙会3啖呃2", publish_date="2026-07-05",
                  plays=10700, likes=57, comments=37, completion_rate=0.3324, saves=5)

    r = client.post("/api/posts/merge", json={"post_ids": [rounded, exact]}).json()
    assert r["merged_into"] == exact, "字段更全的详情页那条该当底稿"

    merged = client.get(f"/api/posts/{exact}").json()
    assert merged["plays"] == 10700, "应保留详情页的精确值，而不是列表页四舍五入的 1.1万"
    assert merged["title"].startswith("同样1200大卡"), "应保留可读的完整标题"
    assert merged["completion_rate"] == 0.3324
    assert "[合并]" in (merged["notes"] or ""), "合并过程要留痕，事后可查"
    assert client.get(f"/api/posts/{rounded}").status_code == 404
    assert client.get("/api/posts/duplicate-candidates").json() == []


def test_merge_moves_snapshots_and_dedupes_them(client, account_id):
    a = _make(client, account_id, title=TRUNCATED, publish_date="2026-07-06", likes=57, comments=7)
    b = _make(client, account_id, title=FULL, publish_date="2026-07-06",
              likes=57, comments=7, completion_rate=0.0129, saves=1)
    snap = {"checked_at": "2026-07-07T05:44:00", "plays": 5359, "likes": 57, "comments": 7}
    client.post(f"/api/posts/{a}/snapshots", json=snap)
    client.post(f"/api/posts/{b}/snapshots", json=snap)   # 完全相同的一条

    r = client.post("/api/posts/merge", json={"post_ids": [a, b]}).json()
    assert r["snapshots_deduped"] == 1
    assert len(client.get(f"/api/posts/{r['merged_into']}/snapshots").json()) == 1


def test_merge_requires_at_least_two(client, account_id):
    a = _make(client, account_id)
    assert client.post("/api/posts/merge", json={"post_ids": [a]}).status_code == 400
