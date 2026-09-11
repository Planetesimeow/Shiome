"""分析与笔记 API 共用的取数函数；按账号组织作品与创作物，不调用模型。"""
import json

# 喂给模型时每条作品带哪些字段。不是全表 —— 无关字段会稀释注意力，也白烧 token。
_POST_FIELDS = [
    "id", "title", "publish_date", "platform", "duration_sec", "plays", "likes",
    "comments", "shares", "saves", "completion_rate", "avg_watch_time",
    "profile_visits", "new_followers", "unfollows", "cover_ctr", "bounce_2s_rate",
    "danmaku_count", "fan_conversion_rate", "high_intent_comments", "high_intent_dms",
    "is_anomaly_period", "notes",
]
_CREATIVE_FIELDS = [
    "id", "label", "media_type", "content_summary", "on_screen_text",
    "music", "hook_description", "content_pillar",
]


def _slim(row: dict, fields: list[str]) -> dict:
    out = {k: row.get(k) for k in fields if row.get(k) not in (None, "")}
    if row.get("platform_data"):
        try:
            out["platform_data"] = json.loads(row["platform_data"])
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def get_post_with_creative(conn, post_id: int) -> dict | None:
    """一条作品 + 它对应的创作物内容画像（如果填了）。"""
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return None
    post = dict(row)
    if post.get("creative_id"):
        c = conn.execute("SELECT * FROM creatives WHERE id = ?",
                         (post["creative_id"],)).fetchone()
        if c:
            post["creative"] = _slim(dict(c), _CREATIVE_FIELDS)
    return post


def recent_posts(conn, account_id: int, limit: int = 20,
                 exclude_anomaly: bool = True) -> list[dict]:
    sql = "SELECT * FROM posts WHERE account_id = ?"
    if exclude_anomaly:
        sql += " AND is_anomaly_period = 0"
    sql += " ORDER BY publish_date DESC LIMIT ?"
    rows = conn.execute(sql, (account_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        slim = _slim(d, _POST_FIELDS)
        if d.get("creative_id"):
            c = conn.execute("SELECT * FROM creatives WHERE id = ?",
                             (d["creative_id"],)).fetchone()
            if c:
                slim["creative"] = _slim(dict(c), _CREATIVE_FIELDS)
        out.append(slim)
    return out


def profiled_creatives(conn, account_id: int, limit: int = 20) -> list[dict]:
    """
    有内容画像的创作物（按最近发布排序）。创作者画像分析看的是这个，
    而不是播放数据 —— 一条创作物发了三个平台也只出现一次。
    """
    rows = conn.execute(
        """SELECT DISTINCT c.*, MAX(p.publish_date) AS last_published
           FROM creatives c JOIN posts p ON p.creative_id = c.id
           WHERE p.account_id = ?
           GROUP BY c.id
           ORDER BY last_published DESC LIMIT ?""",
        (account_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("content_summary") or d.get("hook_description"):
            slim = _slim(d, _CREATIVE_FIELDS)
            slim["last_published"] = d.get("last_published")
            out.append(slim)
    return out


def creator_notes(conn, account_id: int | None = None, post_id: int | None = None,
                  limit: int = 20) -> list[dict]:
    """创作者自己写下的想法。数字说不出"我想往哪个方向转"，这个能。"""
    sql = "SELECT id, body, post_id, creative_id, created_at FROM creator_notes WHERE 1=1"
    params: list = []
    if account_id is not None:
        sql += " AND (account_id = ? OR account_id IS NULL)"
        params.append(account_id)
    if post_id is not None:
        sql += " AND post_id = ?"
        params.append(post_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
