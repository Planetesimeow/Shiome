"""
结构迁移：v1 的一张 videos 表 → v2 的 accounts / creatives / posts / post_snapshots。

三条原则：
1. **不删数据。** 旧表被改名成 _v1_videos / _v1_video_snapshots 留在库里，不 DROP。
   迁移前另外打一份带标记的备份（backups/shiome-pre-v2-*.db）。
2. **只做能确定的合并。** 一模一样的两行（每个字段都相同）可以直接并掉，那不是判断；
   "看起来像同一条"的留给人确认，走 /api/posts/duplicate-candidates。
   靠指标指纹猜着删数据，跟这个项目"任何影响决策的数字都要人过一遍"的规矩是冲突的。
3. **幂等。** schema_migrations 记一笔，跑过就不再跑。
"""
from app.database import get_conn, backup_db
from app.dedupe import dedupe_snapshots

MIGRATION_V2 = "0001_creator_data_model"

# v1 时期这段人设写死在 app/analysis/prompts.py 里。v2 把它变成 accounts.persona 的数据，
# 这里保留一份只为迁移时把老账号的人设填进去 —— prompts.py 里已经不该再有它。
LEGACY_PERSONA = """
账号背景：
- 账号定位：面向在日高净值华人群体的生活方式顾问，内容是信任建立的第一步，
  最终目标是转化为不动产/车辆购置等咨询服务的客户，客户案例再反哺内容。
- 内容公式：体态/体型反差作为钩子 + 热量/宏量营养数据作为"系统感"元素 + 自嘲式幽默作为人设。
- 目标人群体量小、决策周期长、客单价高。账号的"成功"不是泛娱乐意义上的涨粉曲线，
  而是精准触达 + 高转化，粉丝数本身不是核心指标。
- 内容风控：涉及资产、移民身份、大额消费等表述在平台上容易触发限流审查，
  分析时要主动识别这类措辞风险，而不是等被限流才发现。
""".strip()

LEGACY_GOAL_NOTE = "精准触达 > 泛量增长：粉丝数不是核心指标，高意向咨询才是。"

# v1 videos → v2 posts 的同名字段（内容画像字段不在这里，它们要去 creatives）
_CARRY_FIELDS = [
    "title", "publish_date", "duration_sec", "plays", "likes", "comments",
    "shares", "saves", "completion_rate", "avg_watch_time", "profile_visits",
    "new_followers", "unfollows", "danmaku_count", "cover_ctr", "bounce_2s_rate",
    "fan_conversion_rate", "high_intent_comments", "high_intent_dms",
    "is_anomaly_period", "notes", "raw_data",
]
_CREATIVE_FIELDS = ["content_summary", "on_screen_text", "music",
                    "hook_description", "content_pillar"]
# 判定"完全一样的两行"用的键：全字段相同才算，这才是不需要人来判断的情况
_EXACT_KEY_FIELDS = ["title", "publish_date", "plays", "likes", "comments",
                     "shares", "saves", "completion_rate", "douyin_video_id"]


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(conn, table: str, ddl_name: str, ddl_type: str):
    if ddl_name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl_name} {ddl_type}")


def _applied(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = ?", (name,)
    ).fetchone() is not None


def _mark(conn, name: str):
    conn.execute("INSERT OR IGNORE INTO schema_migrations (name) VALUES (?)", (name,))


def ensure_default_account(conn, owner_id: str = "local", platform: str = "douyin",
                           display_name: str | None = None, persona: str | None = None,
                           goal_note: str | None = None) -> int:
    """
    保证至少有一个账号存在。全新安装时建一个**空人设**的账号 ——
    不给新用户塞上一个账号的人设，那会让分析悄悄按别人的定位跑。
    """
    row = conn.execute(
        "SELECT id FROM accounts WHERE owner_id = ? ORDER BY id LIMIT 1", (owner_id,)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO accounts (owner_id, platform, handle, display_name, persona, goal_note)
           VALUES (?,?,?,?,?,?)""",
        (owner_id, platform, None, display_name or "我的账号", persona, goal_note),
    )
    return cur.lastrowid


def _migrate_analysis_results(conn, id_map: dict[int, int]):
    """v1 的 analysis_results.video_id → v2 的 post_id / account_id / creative_id。"""
    cols = _columns(conn, "analysis_results")
    if "post_id" in cols:
        return  # 已经是 v2 形态
    conn.execute("ALTER TABLE analysis_results RENAME TO _v1_analysis_results")
    conn.execute("""
        CREATE TABLE analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER REFERENCES posts(id),
            creative_id INTEGER REFERENCES creatives(id),
            account_id INTEGER REFERENCES accounts(id),
            analysis_type TEXT NOT NULL,
            result_json TEXT NOT NULL,
            model_used TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            duration_ms INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    old_cols = _columns(conn, "_v1_analysis_results")
    extra = [c for c in ("model_used", "input_tokens", "output_tokens", "duration_ms")
             if c in old_cols]
    sel = ", ".join(["video_id", "analysis_type", "result_json"] + extra)
    for r in conn.execute(f"SELECT {sel} FROM _v1_analysis_results").fetchall():
        cols_in = ["post_id", "analysis_type", "result_json"] + extra
        vals = [id_map.get(r["video_id"]) if r["video_id"] is not None else None,
                r["analysis_type"], r["result_json"]] + [r[c] for c in extra]
        conn.execute(
            f"INSERT INTO analysis_results ({','.join(cols_in)}) "
            f"VALUES ({','.join('?' * len(vals))})",
            vals,
        )


def migrate_v1_to_v2(conn) -> dict:
    account_id = ensure_default_account(
        conn, display_name="満電暴走兔", persona=LEGACY_PERSONA, goal_note=LEGACY_GOAL_NOTE
    )

    # 异常期 / 账号级指标：补上 account_id 列
    _add_column(conn, "anomaly_periods", "account_id", "INTEGER")
    _add_column(conn, "account_metrics", "account_id", "INTEGER")
    conn.execute("UPDATE account_metrics SET account_id = ? WHERE account_id IS NULL",
                 (account_id,))

    v1_cols = _columns(conn, "videos")
    carry = [f for f in _CARRY_FIELDS if f in v1_cols]
    creative_fields = [f for f in _CREATIVE_FIELDS if f in v1_cols]

    videos = [dict(r) for r in conn.execute("SELECT * FROM videos ORDER BY id").fetchall()]
    id_map: dict[int, int] = {}   # 旧 video id -> 新 post id
    exact_seen: dict[tuple, int] = {}
    collapsed = 0

    for v in videos:
        key = tuple(v.get(f) for f in _EXACT_KEY_FIELDS if f in v1_cols)
        if key in exact_seen:
            # 每个字段都一样 —— 这不是判断，直接指向同一条 post
            id_map[v["id"]] = exact_seen[key]
            collapsed += 1
            continue

        creative_id = None
        if any(v.get(f) for f in creative_fields):
            cvals = [v.get(f) for f in creative_fields]
            cur = conn.execute(
                f"INSERT INTO creatives (owner_id, label, duration_sec, {','.join(creative_fields)}) "
                f"VALUES (?,?,?,{','.join('?' * len(creative_fields))})",
                ["local", (v.get("title") or "")[:40], v.get("duration_sec")] + cvals,
            )
            creative_id = cur.lastrowid

        cols = ["account_id", "creative_id", "platform", "platform_post_id"] + carry
        vals = [account_id, creative_id, v.get("platform") or "douyin",
                v.get("douyin_video_id")] + [v.get(f) for f in carry]
        cur = conn.execute(
            f"INSERT INTO posts ({','.join(cols)}) VALUES ({','.join('?' * len(vals))})",
            vals,
        )
        id_map[v["id"]] = cur.lastrowid
        exact_seen[key] = cur.lastrowid

    # 快照搬家（旧表里同一条视频可能被重复记了完全相同的快照，一并去重）
    snaps = 0
    if _table_exists(conn, "video_snapshots"):
        snap_cols = _columns(conn, "video_snapshots")
        fields = [f for f in ("checked_at", "plays", "likes", "comments", "shares",
                              "saves", "completion_rate", "profile_visits",
                              "new_followers", "bounce_2s_rate", "source", "curve_note")
                  if f in snap_cols]
        for s in conn.execute("SELECT * FROM video_snapshots ORDER BY id").fetchall():
            post_id = id_map.get(s["video_id"])
            if post_id is None:
                continue  # 孤儿快照（对应视频已不在），丢掉
            conn.execute(
                f"INSERT INTO post_snapshots (post_id, {','.join(fields)}) "
                f"VALUES (?, {','.join('?' * len(fields))})",
                [post_id] + [s[f] for f in fields],
            )
            snaps += 1

    _migrate_analysis_results(conn, id_map)

    snap_removed = sum(dedupe_snapshots(conn, pid) for pid in set(id_map.values()))

    conn.execute("ALTER TABLE videos RENAME TO _v1_videos")
    if _table_exists(conn, "video_snapshots"):
        conn.execute("ALTER TABLE video_snapshots RENAME TO _v1_video_snapshots")

    return {
        "videos_read": len(videos),
        "posts_created": len(set(id_map.values())),
        "exact_duplicates_collapsed": collapsed,
        "snapshots_copied": snaps,
        "snapshots_deduped": snap_removed,
        "account_id": account_id,
    }


def run_migrations():
    """在 init_db() 里调用。跑过一次就不再跑。"""
    with get_conn() as conn:
        already = _applied(conn, MIGRATION_V2)
        has_v1 = _table_exists(conn, "videos")

    if already:
        return None

    if not has_v1:
        # 全新库：没有要迁移的东西，建个空账号占位就行
        with get_conn() as conn:
            ensure_default_account(conn)
            _mark(conn, MIGRATION_V2)
        return None

    backup_db(tag="pre-v2")
    with get_conn() as conn:
        report = migrate_v1_to_v2(conn)
        _mark(conn, MIGRATION_V2)
    print(f"[shiome] v1→v2 迁移完成：{report}")
    print("[shiome] 旧表保留为 _v1_videos / _v1_video_snapshots，没有删除任何数据。")
    return report
