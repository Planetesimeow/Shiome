"""
DEMO 数据播种脚本 —— 只创建全新的演示库，不覆盖任何已有文件。

跑法（PowerShell）：
    $env:SHIOME_DB_PATH='work/demo.db'
    python -m scripts.seed_demo

安全保护：没设 SHIOME_DB_PATH 或目标文件已存在时拒绝执行。

它会：建表 → 填写 demo 账号 → 插 1 个异常期 → 插 5 条 demo 作品
（其中 2 条带内容画像字段，1 条落在异常期）→ 给"体态反差"那条挂 3 个台阶式爬升快照。
5 条作品覆盖多种表现：持续增长 / 高播放低关注 / 异常期 / 中等 / 较低播放。
"""
import os

DEMO_ANOMALY = ("2026-05-01", "2026-05-07", "DEMO：记录方式变化，暂不纳入基线；原因未证实")

# 发布侧字段（平台量出来的数字）
POST_COLS = [
    "title", "publish_date", "duration_sec", "plays", "likes", "comments",
    "shares", "saves", "completion_rate", "avg_watch_time", "profile_visits",
    "new_followers", "high_intent_comments", "high_intent_dms",
]
# 创作侧字段（你做的那个东西）。只有部分视频填，模拟真实录入情况。
CREATIVE_COLS = ["content_summary", "on_screen_text", "music",
                 "hook_description", "content_pillar"]

DEMO_PERSONA = "DEMO 人设：分享生活记录和实用经验，寻找可以持续制作的内容方向。"

DEMO_VIDEOS = [
    # 1) 增长与关注表现较好（下面挂快照的就是这条）
    {
        "platform": "douyin", "title": "体态反差开场：3个月身材变化实录",
        "publish_date": "2026-06-20", "duration_sec": 34, "plays": 42000, "likes": 1500,
        "comments": 320, "shares": 210, "saves": 900, "completion_rate": 0.48,
        "avg_watch_time": 22.0, "profile_visits": 1800, "new_followers": 260,
        "high_intent_comments": 40, "high_intent_dms": 12,
        "content_summary": "开场体型反差，中段用热量/宏量数据讲变化逻辑，结尾自嘲。",
        "on_screen_text": "3个月 -8kg｜每天多算这一步", "music": "轻鼓点 up-tempo",
        "hook_description": "前2秒体型反差画面", "content_pillar": "体态反差",
    },
    # 2) 高播放、关注转化较低
    {
        "platform": "douyin", "title": "热量计算器实测：便利店午餐怎么选",
        "publish_date": "2026-06-15", "duration_sec": 41, "plays": 88000, "likes": 3000,
        "comments": 90, "shares": 60, "saves": 300, "completion_rate": 0.55,
        "avg_watch_time": 18.0, "profile_visits": 400, "new_followers": 30,
        "high_intent_comments": 3, "high_intent_dms": 1,
        "content_summary": "便利店午餐逐个算热量，节奏快、信息密度高。",
        "on_screen_text": "这顿 620 大卡", "music": "热门卡点音",
        "hook_description": "悬念式提问'哪个更肥'", "content_pillar": "系统感数据",
    },
    # 3) 已标记异常期；低播放本身不能说明原因
    {
        "platform": "douyin", "title": "在日买房避坑：地段 vs 预算怎么权衡",
        "publish_date": "2026-05-03", "duration_sec": 58, "plays": 600, "likes": 20,
        "comments": 5, "shares": 2, "saves": 15, "completion_rate": 0.40,
        "avg_watch_time": 15.0, "profile_visits": 30, "new_followers": 3,
        "high_intent_comments": 2, "high_intent_dms": 1,
    },
    # 4) 中等表现
    {
        "platform": "douyin", "title": "自嘲：健身教练看到我的饮食记录",
        "publish_date": "2026-06-10", "duration_sec": 29, "plays": 15000, "likes": 800,
        "comments": 110, "shares": 70, "saves": 260, "completion_rate": 0.50,
        "avg_watch_time": 20.0, "profile_visits": 500, "new_followers": 70,
        "high_intent_comments": 8, "high_intent_dms": 3,
    },
    # 5) 自然衰减 / 偏弱
    {
        "platform": "douyin", "title": "宏量营养入门：蛋白质到底怎么算",
        "publish_date": "2026-06-25", "duration_sec": 47, "plays": 5200, "likes": 120,
        "comments": 18, "shares": 8, "saves": 60, "completion_rate": 0.32,
        "avg_watch_time": 12.0, "profile_visits": 90, "new_followers": 8,
        "high_intent_comments": 1, "high_intent_dms": 0,
    },
]

# 台阶式健康爬升快照，挂到第 1 条视频。(checked_at, plays, likes, comments, shares, saves, completion_rate, profile_visits, new_followers)
DEMO_SNAPSHOTS = [
    ("2026-06-20T12:00:00", 800, 40, 12, 6, 30, 0.50, 60, 10),
    ("2026-06-21T11:00:00", 12000, 500, 120, 80, 350, 0.49, 700, 110),
    ("2026-06-23T11:00:00", 42000, 1500, 320, 210, 900, 0.48, 1800, 260),
]


def main():
    if not os.environ.get("SHIOME_DB_PATH"):
        raise SystemExit("拒绝执行：请设置 SHIOME_DB_PATH 指向尚不存在的演示库。")
    from app.database import init_db, get_conn, post_falls_in_anomaly, DB_PATH
    from app.migrations import ensure_default_account

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation also closes the race between checking and writing.
        with DB_PATH.open("xb"):
            pass
    except FileExistsError:
        raise SystemExit("拒绝执行：目标已存在，请选择新的演示库路径。")
    init_db()
    with get_conn() as conn:
        account_id = ensure_default_account(conn)
        conn.execute(
            """UPDATE accounts SET display_name='DEMO 账号', persona=?,
               goal_note='稳定内容方向，提升观看和涨粉' WHERE id=?""",
            (DEMO_PERSONA, account_id),
        )

        conn.execute(
            "INSERT INTO anomaly_periods (start_date, end_date, reason) VALUES (?,?,?)",
            DEMO_ANOMALY,
        )

        first_post_id = None
        n_creatives = 0
        for v in DEMO_VIDEOS:
            # 内容画像去 creatives（发多个平台只描述一次），数据去 posts
            creative_id = None
            if any(v.get(c) for c in CREATIVE_COLS):
                cols = [c for c in CREATIVE_COLS if v.get(c)]
                creative_id = conn.execute(
                    f"INSERT INTO creatives (owner_id, label, duration_sec, {','.join(cols)}) "
                    f"VALUES ('local', ?, ?, {','.join('?' * len(cols))})",
                    [v["title"][:40], v.get("duration_sec")] + [v[c] for c in cols],
                ).lastrowid
                n_creatives += 1

            anomaly = post_falls_in_anomaly(conn, account_id, v["publish_date"])
            cur = conn.execute(
                f"INSERT INTO posts (account_id, creative_id, platform, is_anomaly_period, "
                f"{','.join(POST_COLS)}) "
                f"VALUES (?,?,'douyin',?,{','.join('?' * len(POST_COLS))})",
                [account_id, creative_id, int(anomaly)] + [v.get(c) for c in POST_COLS],
            )
            if first_post_id is None:
                first_post_id = cur.lastrowid

        for snap in DEMO_SNAPSHOTS:
            conn.execute(
                """INSERT INTO post_snapshots
                   (post_id, checked_at, plays, likes, comments, shares, saves,
                    completion_rate, profile_visits, new_followers)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (first_post_id, *snap),
            )

    print(f"✅ DEMO 数据已写入 {DB_PATH}")
    print(f"   - 1 个账号（account_id={account_id}，带 DEMO 人设）")
    print(f"   - {len(DEMO_VIDEOS)} 条作品（post_id 从 {first_post_id} 起），其中 {n_creatives} 条有内容画像")
    print(f"   - 1 个异常期 {DEMO_ANOMALY[0]}~{DEMO_ANOMALY[1]}")
    print(f"   - {len(DEMO_SNAPSHOTS)} 个快照挂在 post_id={first_post_id}（体态反差那条，用来测扩散诊断）")


if __name__ == "__main__":
    main()
