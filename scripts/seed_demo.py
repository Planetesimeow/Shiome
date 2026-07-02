"""
DEMO 数据播种脚本 —— 仅供本地压测，不要用于真实数据。

跑法（必须用一次性测试库，别污染真实 douyin.db）：
    SHIOME_DB_PATH=test_output/2026-07-02_Test.db python -m scripts.seed_demo

安全保护：没设 SHIOME_DB_PATH 时直接拒绝执行，避免误写真实库。

它会（在测试库里）：建表 → 清空旧数据 → 插 1 个异常期 → 插 5 条抖音 demo 视频
（其中 2 条带内容画像字段，1 条落在异常期）→ 给"体态反差"那条挂 3 个台阶式爬升快照。
5 条视频刻意覆盖不同形态：健康爬升 / 高播放低意向(泛量) / 异常期冻结 / 中等 / 自然衰减。
"""
import os

# 安全闸：只允许写入显式指定的测试库
if not os.environ.get("SHIOME_DB_PATH"):
    raise SystemExit(
        "拒绝执行：请先设置 SHIOME_DB_PATH 指向一次性测试库，避免污染真实 douyin.db。\n"
        "例：SHIOME_DB_PATH=test_output/2026-07-02_Test.db python -m scripts.seed_demo"
    )

from app.database import init_db, get_conn, video_falls_in_anomaly, DB_PATH

DEMO_ANOMALY = ("2026-05-01", "2026-05-07", "DEMO：新号 IP+地理标签触发限流")

# 视频字段（platform 固定 douyin）。content_* 字段只有部分视频填，模拟真实录入情况。
VIDEO_COLS = [
    "platform", "title", "publish_date", "duration_sec", "plays", "likes", "comments",
    "shares", "saves", "completion_rate", "avg_watch_time", "profile_visits",
    "new_followers", "high_intent_comments", "high_intent_dms",
    "content_summary", "on_screen_text", "music", "hook_description", "content_pillar",
]

DEMO_VIDEOS = [
    # 1) 健康爬升 + 高精准信号（下面挂快照的就是这条）
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
    # 2) 高播放低意向（泛量陷阱）
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
    # 3) 异常期内 —— 冻结/限流形态
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
    init_db()
    with get_conn() as conn:
        # 测试库是一次性的：清空后重播，保证可重复运行
        for t in ("video_snapshots", "analysis_results", "videos", "anomaly_periods"):
            conn.execute(f"DELETE FROM {t}")

        conn.execute(
            "INSERT INTO anomaly_periods (start_date, end_date, reason) VALUES (?,?,?)",
            DEMO_ANOMALY,
        )

        placeholders = ",".join(["?"] * (len(VIDEO_COLS) + 1))  # +1 = is_anomaly_period
        sql = (
            f"INSERT INTO videos ({','.join(VIDEO_COLS)}, is_anomaly_period) "
            f"VALUES ({placeholders})"
        )
        first_video_id = None
        for v in DEMO_VIDEOS:
            anomaly = video_falls_in_anomaly(conn, v["publish_date"])
            values = tuple(v.get(c) for c in VIDEO_COLS) + (int(anomaly),)
            cur = conn.execute(sql, values)
            if first_video_id is None:
                first_video_id = cur.lastrowid

        for snap in DEMO_SNAPSHOTS:
            conn.execute(
                """INSERT INTO video_snapshots
                   (video_id, checked_at, plays, likes, comments, shares, saves,
                    completion_rate, profile_visits, new_followers)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (first_video_id, *snap),
            )

    print(f"✅ DEMO 数据已写入 {DB_PATH}")
    print(f"   - {len(DEMO_VIDEOS)} 条视频（video_id 从 {first_video_id} 起）")
    print(f"   - 1 个异常期 {DEMO_ANOMALY[0]}~{DEMO_ANOMALY[1]}")
    print(f"   - {len(DEMO_SNAPSHOTS)} 个快照挂在 video_id={first_video_id}（体态反差那条，用来测扩散诊断）")


if __name__ == "__main__":
    main()
