"""
"关于这个创作者，我们知道什么" —— 集中在一个地方组装。

v1 时每个分析端点自己在 main.py 里 SELECT 一遍自己要的数据，五份互不相同的取数逻辑。
这里把它收成一处，眼下的好处是基线口径不会各算各的；更重要的是，Phase 5 的对话式助手
需要的正是同一份东西 —— 助手要"懂你"，靠的就是这份上下文。所以这不是给未来留的空壳，
是今天就在用、将来直接复用的那一层（roadmap 里说的 socket）。

刻意的边界：这里只负责**取数和组织**，不负责判断，也不调模型。
"""
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


def recent_account_metrics(conn, account_id: int, limit: int = 6) -> list[dict]:
    rows = conn.execute(
        """SELECT captured_at, period, plays, profile_visits, net_followers,
                  unfollows, completion_rate, search_views, cover_ctr
           FROM account_metrics WHERE account_id = ?
           ORDER BY captured_at DESC LIMIT ?""",
        (account_id, limit),
    ).fetchall()
    return [{k: v for k, v in dict(r).items() if v is not None} for r in rows]


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


def build_creator_context(conn, account_id: int, *, recent_limit: int = 20,
                          post_id: int | None = None,
                          include_notes: bool = True) -> dict:
    """
    一份完整的"这个创作者现在是什么状态"。分析模块按需取其中几块；
    Phase 5 的助手整份用，并按对话内容决定展开哪一部分。
    """
    from app.analysis.prompts import compute_baseline, get_account
    from app.database import get_snapshots

    ctx: dict = {
        "account": get_account(conn, account_id),
        "baseline": compute_baseline(conn, account_id),
        "recent_posts": recent_posts(conn, account_id, recent_limit),
        "account_metrics": recent_account_metrics(conn, account_id),
    }
    if include_notes:
        ctx["creator_notes"] = creator_notes(conn, account_id, post_id=post_id)
    if post_id is not None:
        ctx["post"] = get_post_with_creative(conn, post_id)
        ctx["snapshots"] = get_snapshots(conn, post_id)
    return ctx
