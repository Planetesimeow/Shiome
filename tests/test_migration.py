"""
v1 → v2 结构迁移。

用一个合成的 v1 库来测，形状照着真实线上库来：同一条视频被列表页和详情页各记了一次
（标题一个截断一个完整、OCR 还读错了字），外加一对一模一样的重复行。

迁移必须做到三件事：不删数据、只合并能确定的、幂等。
"""
import sqlite3

import pytest

V1_SCHEMA = """
CREATE TABLE videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL DEFAULT 'douyin',
    douyin_video_id TEXT, title TEXT NOT NULL, publish_date TEXT NOT NULL,
    duration_sec INTEGER, plays INTEGER DEFAULT 0, likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, saves INTEGER DEFAULT 0,
    completion_rate REAL, avg_watch_time REAL, profile_visits INTEGER DEFAULT 0,
    new_followers INTEGER DEFAULT 0, high_intent_comments INTEGER DEFAULT 0,
    high_intent_dms INTEGER DEFAULT 0, is_anomaly_period INTEGER DEFAULT 0,
    notes TEXT, raw_data TEXT, content_summary TEXT, on_screen_text TEXT,
    music TEXT, hook_description TEXT, content_pillar TEXT, danmaku_count INTEGER,
    cover_ctr REAL, bounce_2s_rate REAL, unfollows INTEGER, fan_conversion_rate REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE video_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL,
    checked_at TEXT NOT NULL, plays INTEGER, likes INTEGER, comments INTEGER,
    shares INTEGER, saves INTEGER, completion_rate REAL, profile_visits INTEGER,
    new_followers INTEGER, bounce_2s_rate REAL, source TEXT DEFAULT 'manual',
    curve_note TEXT
);
CREATE TABLE anomaly_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT, start_date TEXT NOT NULL,
    end_date TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER, analysis_type TEXT NOT NULL,
    result_json TEXT NOT NULL, model_used TEXT, input_tokens INTEGER,
    output_tokens INTEGER, duration_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE account_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL, period TEXT,
    plays INTEGER, profile_visits INTEGER, likes INTEGER, comments INTEGER,
    shares INTEGER, net_followers INTEGER, unfollows INTEGER, completion_rate REAL,
    search_views INTEGER, cover_ctr REAL, danmaku INTEGER, peer_percentiles TEXT,
    raw_json TEXT, source TEXT DEFAULT 'vision'
);
"""

TRUNCATED = "六块腹肌的日本大厂程序员放松日吃了啥？又到我最爱的放松日啦～来一起看看今天都吃了些啥吧！#..."
FULL = ("六块腹肌的日本大厂程序员放纵日吃了啥？又到我最爱的放纵日啦~来一起看看今天都吃了些啥吧！"
        "#放纵日吃点啥 #上班族减脂 #程序员减脂 #薄肌养成")


@pytest.fixture
def v1_db(tmp_path, monkeypatch):
    """造一个 v1 形状的库，形状照着真实线上库。"""
    from app import database

    path = tmp_path / "v1.db"
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    conn.executemany(
        """INSERT INTO videos (title, publish_date, plays, likes, comments, saves,
                               completion_rate, content_summary, hook_description)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [
            (TRUNCATED, "2026-07-06", 5355, 57, 7, 0, None, None, None),      # 1 列表页
            (FULL, "2026-07-06", 5359, 57, 7, 1, 0.0129, None, None),         # 2 详情页
            ("仙会3啖呃2", "2026-07-05", 10700, 57, 37, 5, 0.3324, None, None),  # 3
            ("仙会3啖呃2", "2026-07-05", 10700, 57, 37, 5, 0.3324, None, None),  # 4 完全相同
            ("带内容画像的一条", "2026-06-19", 1811, 31, 6, 3, 0.0136, "拍了什么", "核心钩子"),
        ],
    )
    snap = ("2026-07-07T05:44:00", 5359, 57, 7, 1, 0.0129, "vision", "[每小时] 单峰")
    conn.executemany(
        """INSERT INTO video_snapshots (video_id, checked_at, plays, likes, comments,
                                        saves, completion_rate, source, curve_note)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [(2,) + snap, (2,) + snap, (3,) + snap, (4,) + snap],   # 2 有两条一模一样的
    )
    conn.execute("INSERT INTO anomaly_periods (start_date, end_date, reason) VALUES (?,?,?)",
                 ("2026-03-01", "2026-03-07", "测试异常期"))
    conn.execute("""INSERT INTO analysis_results (video_id, analysis_type, result_json)
                    VALUES (2, 'enhancement', '{"diagnosis": []}')""")
    conn.execute("""INSERT INTO account_metrics (captured_at, period, plays, search_views)
                    VALUES ('2026-07-07T14:43:51', '近30天', 28000, 652)""")
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", path)
    return path


def _rows(path, sql):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def test_migration_collapses_only_identical_rows(v1_db):
    from app.database import init_db
    init_db()
    posts = _rows(v1_db, "SELECT * FROM posts ORDER BY id")
    # 5 条进，4 条出：只有那对一模一样的被并掉了
    assert len(posts) == 4
    titles = [p["title"] for p in posts]
    assert TRUNCATED in titles and FULL in titles, "只是相似的两条不该被自动合并"


def test_near_duplicates_are_left_for_the_creator_to_confirm(v1_db):
    from app.database import init_db, get_conn
    from app.dedupe import find_duplicate_candidates
    init_db()
    with get_conn() as conn:
        groups = find_duplicate_candidates(conn)
    assert len(groups) == 1
    assert "标题高度相似" in groups[0]["reason"]


def test_migration_preserves_v1_tables(v1_db):
    """不删数据：旧表改名保留，不 DROP。"""
    from app.database import init_db
    init_db()
    assert len(_rows(v1_db, "SELECT * FROM _v1_videos")) == 5
    assert len(_rows(v1_db, "SELECT * FROM _v1_video_snapshots")) == 4


def test_migration_seeds_the_account_with_the_legacy_persona(v1_db):
    from app.database import init_db
    init_db()
    accounts = _rows(v1_db, "SELECT * FROM accounts")
    assert len(accounts) == 1
    assert accounts[0]["platform"] == "douyin"
    assert "账号定位" in accounts[0]["persona"], "老账号的人设要从源码搬进数据里"


def test_migration_moves_content_profile_into_a_creative(v1_db):
    from app.database import init_db
    init_db()
    creatives = _rows(v1_db, "SELECT * FROM creatives")
    assert len(creatives) == 1, "只有真的填了内容画像的那条才建 creative"
    assert creatives[0]["hook_description"] == "核心钩子"
    linked = _rows(v1_db, "SELECT * FROM posts WHERE creative_id IS NOT NULL")
    assert len(linked) == 1 and linked[0]["title"] == "带内容画像的一条"


def test_migration_dedupes_snapshots_and_repoints_analyses(v1_db):
    from app.database import init_db
    init_db()
    snaps = _rows(v1_db, "SELECT * FROM post_snapshots")
    assert len(snaps) == 2, "两条一模一样的快照留一条；被合并的那条的快照并过来也去重"
    results = _rows(v1_db, "SELECT * FROM analysis_results")
    assert len(results) == 1 and results[0]["post_id"] is not None


def test_account_metrics_get_an_account(v1_db):
    from app.database import init_db
    init_db()
    metrics = _rows(v1_db, "SELECT * FROM account_metrics")
    assert metrics[0]["account_id"] is not None


def test_migration_is_idempotent(v1_db):
    from app.database import init_db
    init_db()
    first = _rows(v1_db, "SELECT * FROM posts")
    init_db()
    init_db()
    assert _rows(v1_db, "SELECT * FROM posts") == first, "跑第二遍不该再动数据"


def test_fresh_database_gets_an_empty_persona_account(tmp_path, monkeypatch):
    """全新安装不该继承别人的人设。"""
    from app import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "fresh.db")
    database.init_db()
    accounts = _rows(tmp_path / "fresh.db", "SELECT * FROM accounts")
    assert len(accounts) == 1 and not accounts[0]["persona"]
