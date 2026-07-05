"""
数据层。用 SQLite，单文件、零配置，够一个人用的账号规模。
以后如果要多端同步，再考虑换 Postgres —— 结构不用大改。
"""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# 默认落在 app/data/douyin.db；设 SHIOME_DB_PATH 可指向别处（比如压测时用一次性测试库，
# 不污染真实数据）。
_DEFAULT_DB_PATH = Path(__file__).parent / "data" / "douyin.db"
DB_PATH = Path(os.environ.get("SHIOME_DB_PATH", _DEFAULT_DB_PATH))

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL DEFAULT 'douyin',  -- v1.0.0 只有 douyin；小红书/B站 v2.0.0
    douyin_video_id TEXT,
    title TEXT NOT NULL,
    publish_date TEXT NOT NULL,          -- ISO date
    duration_sec INTEGER,
    plays INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,             -- 收藏，判断"高意向但没互动"的人群
    completion_rate REAL,                -- 完播率 0-1
    avg_watch_time REAL,                 -- 秒
    profile_visits INTEGER DEFAULT 0,    -- 主页访问数
    new_followers INTEGER DEFAULT 0,     -- 该视频带来的净增粉丝
    high_intent_comments INTEGER DEFAULT 0,  -- 手动标记：问价/问流程等强意向评论数
    high_intent_dms INTEGER DEFAULT 0,       -- 手动标记：强意向私信数
    is_anomaly_period INTEGER DEFAULT 0, -- 是否落在已知异常期(限流/封控)内，自动从 anomaly_periods 计算
    notes TEXT,
    raw_data TEXT,                       -- 原始导出字段的 JSON 备份，方便以后补字段不用重新导入
    -- 以下是内容画像字段，创作者中心导不出来，只能手动录入，供 creator_profile 分析用
    content_summary TEXT,                -- 内容简述：这条视频拍了什么
    on_screen_text TEXT,                 -- 画面文字/字幕要点
    music TEXT,                          -- 配乐
    hook_description TEXT,               -- 核心抓人点
    content_pillar TEXT,                 -- 内容方向标签，比如"体态反差"/"买车避坑"
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS anomaly_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT NOT NULL                 -- 例如 "新号IP+地理标签触发限流"
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER,                    -- NULL 表示账号级/组合分析，而不是单条视频
    analysis_type TEXT NOT NULL,         -- enhancement / content_ideas / trend_forecast / pool_diagnosis / creator_profile
    result_json TEXT NOT NULL,
    model_used TEXT,
    input_tokens INTEGER,                -- 成本可见性：这次分析花了多少 token
    output_tokens INTEGER,
    duration_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);

-- 时间序列快照。流量池定位靠的是曲线形状/爬升速度，不是终态数字，
-- 所以需要你在固定时间点（比如发布后1小时、24小时、3天）手动查一次创作者中心并记录。
CREATE TABLE IF NOT EXISTS video_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    checked_at TEXT NOT NULL,            -- ISO datetime，你查看的那一刻
    plays INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    saves INTEGER,
    completion_rate REAL,
    profile_visits INTEGER,
    new_followers INTEGER,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
"""

# videos 表在功能一开始上线之后新增的列。用 ALTER TABLE 做幂等迁移，
# 已经存在的列会报错，直接吞掉即可 —— 这样旧数据库文件也能无痛升级。
MIGRATIONS = [
    "ALTER TABLE videos ADD COLUMN content_summary TEXT",
    "ALTER TABLE videos ADD COLUMN on_screen_text TEXT",
    "ALTER TABLE videos ADD COLUMN music TEXT",
    "ALTER TABLE videos ADD COLUMN hook_description TEXT",
    "ALTER TABLE videos ADD COLUMN content_pillar TEXT",
    "ALTER TABLE videos ADD COLUMN platform TEXT NOT NULL DEFAULT 'douyin'",
    # 每次分析的成本可见性：token 用量 + 耗时
    "ALTER TABLE analysis_results ADD COLUMN input_tokens INTEGER",
    "ALTER TABLE analysis_results ADD COLUMN output_tokens INTEGER",
    "ALTER TABLE analysis_results ADD COLUMN duration_ms INTEGER",
]


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        for stmt in MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # 列已经存在，正常情况


def backup_db(keep: int = 10):
    """
    每天第一次启动时把数据库快照备份到 <db目录>/backups/，保留最近 keep 份。
    动机：快照/内容画像是手动录入的、没有其他来源，而数据库文件又住在 Dropbox
    同步目录里（同步工具抓到写入中途的库文件有损坏风险）。时点快照文件对同步是安全的。
    用 sqlite 官方 backup API 而不是直接 copy，避免拷到写入一半的状态。
    """
    if not DB_PATH.exists():
        return None
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date
    dest = backup_dir / f"{DB_PATH.stem}-{date.today().isoformat()}{DB_PATH.suffix}"
    if dest.exists():
        return None  # 今天已备份过
    src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(backup_dir.glob(f"{DB_PATH.stem}-*{DB_PATH.suffix}"))[:-keep]:
        old.unlink()
    return dest


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def video_falls_in_anomaly(conn, publish_date: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM anomaly_periods WHERE ? BETWEEN start_date AND end_date LIMIT 1",
        (publish_date,),
    ).fetchone()
    return row is not None


def get_snapshots(conn, video_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM video_snapshots WHERE video_id = ? ORDER BY checked_at ASC",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]
