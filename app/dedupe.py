"""
同一条作品被记成两行，怎么发现、怎么合并。

问题从哪来：截图是主要数据来源，而同一条视频在不同页面上长得不一样 ——
作品列表页的标题是截断的（"...结尾"），详情页是完整的；OCR 还会把字读错
（真实数据里出现过 放松/放纵、大厂/大广、以及一整个标题被读成"仙会3啖呃2"）。
v1 按 (标题, 发布日期) 精确匹配，于是同一条视频进了两行。

这里的原则跟截图入库一样：**发现由机器做，合并由人确认**。
自动合并意味着靠猜去删数据 —— 在一个"任何影响决策的数字都要人过一遍"的工具里，
那是不能开的口子。所以这里只产出候选和判断依据，真正的合并要调用方明确调用。
"""
from difflib import SequenceMatcher

# 判定为"疑似同一条"的标题相似度门槛。0.85 是照着真实数据定的：
# 放松日/放纵日 那组算出来约 0.93，大厂/大广 那组约 0.98，都能过；
# 而不同选题的两条视频通常远低于它。
TITLE_SIMILARITY_THRESHOLD = 0.85

# 合并时按"越晚采集越大"处理的累计型字段
COUNTER_FIELDS = [
    "plays", "likes", "comments", "shares", "saves", "profile_visits",
    "new_followers", "unfollows", "danmaku_count",
    "high_intent_comments", "high_intent_dms",
]
# 比率/时长型：没有"越大越对"的语义，缺了才从别的行补
RATIO_FIELDS = [
    "completion_rate", "avg_watch_time", "cover_ctr",
    "bounce_2s_rate", "fan_conversion_rate", "duration_sec",
]
FILL_FIELDS = COUNTER_FIELDS + RATIO_FIELDS + [
    "platform_post_id", "creative_id", "raw_data", "platform_data",
]

_ELLIPSIS = ("...", "…", "..", "。。。")


def normalize_title(title: str | None) -> str:
    """去掉截断省略号和首尾空白 —— 列表页标题就是靠这些结尾的。"""
    t = (title or "").strip()
    for e in _ELLIPSIS:
        while t.endswith(e):
            t = t[: -len(e)].strip()
    return t


def title_similarity(a: str | None, b: str | None) -> float:
    """
    只比较两个标题**重叠的那一段**：短的那个通常是被截断的版本，
    拿它的长度去截长的那个再比，截断本身就不会被算成"不像"。
    """
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    n = min(len(na), len(nb))
    if n < 4:  # 太短的标题（OCR 残片）不靠标题判断，交给指标指纹
        return 0.0
    return SequenceMatcher(None, na[:n], nb[:n]).ratio()


def _fingerprint_match(a: dict, b: dict) -> bool:
    """
    指标指纹：同一天发布 + 点赞数和评论数都完全相同 + 都不为 0。
    用来兜住标题完全读错的情况（"仙会3啖呃2" 那种，跟真标题一点都不像，
    但点赞 57 / 评论 37 跟另一行分毫不差）。
    """
    return bool(
        a.get("likes") and b.get("likes")
        and a.get("comments") and b.get("comments")
        and a["likes"] == b["likes"]
        and a["comments"] == b["comments"]
    )


def find_duplicate_candidates(conn, account_id: int | None = None) -> list[dict]:
    """
    返回疑似重复的分组：[{post_ids, reason, posts:[...]}, ...]。
    只在同一个账号 + 同一个发布日期内部找 —— 跨天的"像"基本都是误报。
    """
    sql = "SELECT * FROM posts"
    params: list = []
    if account_id is not None:
        sql += " WHERE account_id = ?"
        params.append(account_id)
    sql += " ORDER BY publish_date DESC, id"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    buckets: dict[tuple, list[dict]] = {}
    for r in rows:
        buckets.setdefault((r["account_id"], r["publish_date"]), []).append(r)

    groups = []
    for (_acct, _date), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        # 并查集：把桶里两两相似的行连成一组（A~B、B~C 时 A/C 也算同一组）
        parent = {r["id"]: r["id"] for r in bucket}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        reasons: dict[int, set] = {r["id"]: set() for r in bucket}
        for i, a in enumerate(bucket):
            for b in bucket[i + 1:]:
                sim = title_similarity(a["title"], b["title"])
                why = None
                if sim >= TITLE_SIMILARITY_THRESHOLD:
                    why = f"标题高度相似（{sim:.0%}），像是同一条的截断版与完整版"
                elif _fingerprint_match(a, b):
                    why = (f"同日发布且点赞({a['likes']})/评论({a['comments']})完全相同，"
                           f"标题疑似被 OCR 读错")
                if why:
                    ra, rb = find(a["id"]), find(b["id"])
                    if ra != rb:
                        parent[rb] = ra
                    reasons[find(a["id"])].add(why)

        clustered: dict[int, list[dict]] = {}
        for r in bucket:
            clustered.setdefault(find(r["id"]), []).append(r)
        for root, members in clustered.items():
            if len(members) < 2:
                continue
            groups.append({
                "post_ids": [m["id"] for m in members],
                "publish_date": members[0]["publish_date"],
                "account_id": members[0]["account_id"],
                "reason": "；".join(sorted(reasons.get(root, {"疑似重复"}))),
                "posts": [
                    {k: m.get(k) for k in
                     ("id", "title", "plays", "likes", "comments", "saves",
                      "completion_rate", "platform_post_id", "creative_id", "notes")}
                    for m in members
                ],
            })
    return groups


def _richness(post: dict) -> int:
    """有多少个指标字段是真的填了值 —— 详情页截来的行会比列表页截来的行富。"""
    return sum(1 for f in COUNTER_FIELDS + RATIO_FIELDS
               if post.get(f) not in (None, 0))


def merge_posts(conn, post_ids: list[int]) -> dict:
    """
    把多行合并成一行。规则（刻意写得能解释给人听）：
    - 底稿取字段最全的那行（并列时取 id 最大的，也就是最近采集的那次）；
      详情页截图比列表页截图富，所以底稿天然是更精确的那份
      （比如播放量取到 10700 而不是列表页四舍五入的 "1.1万"=11000）。
    - 底稿里为空或为 0 的字段，从其他行补：累计型取最大值，比率型取第一个非空。
    - 标题取最长的那个（截断的那份信息更少）。
    - 快照全部挂到底稿上，内容完全相同的只留一份。
    - 分析结果重新指向底稿。
    - 合并过程写进 notes，事后可查。
    """
    if len(post_ids) < 2:
        raise ValueError("合并至少需要两条")
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM posts WHERE id IN ({','.join('?' * len(post_ids))})", post_ids
    ).fetchall()]
    if len(rows) != len(post_ids):
        raise ValueError("有 post 不存在")
    if len({r["account_id"] for r in rows}) > 1:
        raise ValueError("不能跨账号合并")

    base = max(rows, key=lambda r: (_richness(r), r["id"]))
    others = [r for r in rows if r["id"] != base["id"]]

    updates = {}
    for f in FILL_FIELDS:
        cur = base.get(f)
        if cur not in (None, 0):
            continue
        vals = [o.get(f) for o in others if o.get(f) not in (None, 0)]
        if not vals:
            continue
        updates[f] = max(vals) if f in COUNTER_FIELDS else vals[0]

    longest = max(rows, key=lambda r: len(normalize_title(r["title"])))
    if longest["id"] != base["id"]:
        updates["title"] = longest["title"]

    merged_note = (f"[合并] 由 {len(rows)} 条重复记录合并而成"
                   f"（原 id: {sorted(r['id'] for r in rows)}，底稿 id {base['id']}）")
    updates["notes"] = "\n".join(filter(None, [base.get("notes"), merged_note]))

    conn.execute(
        f"UPDATE posts SET {', '.join(f'{k} = ?' for k in updates)} WHERE id = ?",
        list(updates.values()) + [base["id"]],
    )

    other_ids = [o["id"] for o in others]
    placeholders = ",".join("?" * len(other_ids))
    conn.execute(f"UPDATE post_snapshots SET post_id = ? WHERE post_id IN ({placeholders})",
                 [base["id"]] + other_ids)
    conn.execute(f"UPDATE analysis_results SET post_id = ? WHERE post_id IN ({placeholders})",
                 [base["id"]] + other_ids)
    conn.execute(f"DELETE FROM posts WHERE id IN ({placeholders})", other_ids)

    removed = dedupe_snapshots(conn, base["id"])
    return {"merged_into": base["id"], "removed_posts": other_ids,
            "snapshots_deduped": removed}


def dedupe_snapshots(conn, post_id: int) -> int:
    """同一条 post 下内容完全相同的快照只留最早的一条。返回删了几条。"""
    rows = conn.execute(
        """SELECT id, checked_at, plays, likes, comments, shares, saves,
                  completion_rate, curve_note
           FROM post_snapshots WHERE post_id = ? ORDER BY id""",
        (post_id,),
    ).fetchall()
    seen, doomed = set(), []
    for r in rows:
        key = (r["checked_at"], r["plays"], r["likes"], r["comments"],
               r["shares"], r["saves"], r["completion_rate"], r["curve_note"])
        if key in seen:
            doomed.append(r["id"])
        else:
            seen.add(key)
    if doomed:
        conn.execute(
            f"DELETE FROM post_snapshots WHERE id IN ({','.join('?' * len(doomed))})",
            doomed,
        )
    return len(doomed)
