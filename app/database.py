"""
数据层。SQLite，单文件、零配置，够一个创作者的规模用很久。
以后真的有第二个用户登录了再谈 Postgres —— 结构不用大改。

v2 的核心变化：一张 videos 表拆成四张。
- accounts   一个创作者在一个平台上的账号（人设存在这里，不再写死在 prompts.py）
- creatives  你做出来的那个东西（钩子/画面文字/配乐/内容方向），与平台无关，只描述一次
- posts      一个 creative 发到一个账号上（播放/完播/收藏这些平台量出来的数字）
- post_snapshots  某条 post 的时序快照

为什么要拆：一条视频同时发抖音/小红书/B站，是"一个创作决定 + 三套完全不同的数字"。
混在一张表里，内容画像要填三遍，而且永远问不出"同一个钩子在这个平台活了、在那个平台
死了，说明两边分别推给了谁"——而那个问题才是把三个平台放进一个工具的理由。
详见 docs/design.md。
"""
import os
import shutil
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# 默认落在 app/data/shiome.db；设 SHIOME_DB_PATH 可指向别处（比如测试用一次性库，
# 不污染真实数据）。v1 时期这个文件叫 douyin.db —— 工具已经不只服务抖音了，改名，
# 但旧文件不动（见 _adopt_legacy_db）。
_DEFAULT_DB_PATH = Path(__file__).parent / "data" / "shiome.db"
_LEGACY_DB_PATH = Path(__file__).parent / "data" / "douyin.db"
DB_PATH = Path(os.environ.get("SHIOME_DB_PATH", _DEFAULT_DB_PATH))

SCHEMA = """
-- 一个创作者在一个平台上的账号。owner_id 是多用户的预留：
-- 当前鉴权与前端仍是单用户；预留字段不代表已实现租户隔离。
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL DEFAULT 'local',
    platform TEXT NOT NULL,              -- douyin / xiaohongshu / bilibili
    handle TEXT,                         -- 平台上的账号 ID / 用户名
    display_name TEXT,
    persona TEXT,                        -- 账号人设，喂给所有分析 prompt
    goal_note TEXT,                      -- 这个账号的成功定义（精准触达？泛量？）
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_id, platform, handle)
);

-- 创作物：你做出来的那个东西，跟平台无关。内容画像挂在这里 —— 一条视频发三个平台，
-- 这些字段只填一次。创作者中心导不出来，只能手动填或（Phase 2）从视频文件里提取。
CREATE TABLE IF NOT EXISTS creatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL DEFAULT 'local',
    label TEXT,                          -- 内部代号，方便你自己认
    media_type TEXT DEFAULT 'video',     -- video / image_text（小红书图文笔记）
    duration_sec INTEGER,
    content_summary TEXT,                -- 内容简述：这条拍了什么
    on_screen_text TEXT,                 -- 画面文字/字幕要点
    music TEXT,                          -- 配乐
    hook_description TEXT,               -- 核心抓人点
    content_pillar TEXT,                 -- 内容方向标签，比如"体态反差"
    source_file TEXT,                    -- Phase 2：上传的视频文件引用
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 发布：一个 creative 发到一个账号上。平台量出来的数字都在这里。
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    creative_id INTEGER REFERENCES creatives(id),   -- 可空：数据先进来、内容画像后补
    platform TEXT NOT NULL,              -- 冗余存一份（= account 的 platform），查询方便
    platform_post_id TEXT,               -- 平台侧作品 ID（v1 的 douyin_video_id）
    title TEXT NOT NULL,                 -- 平台上的标题/文案
    publish_date TEXT NOT NULL,          -- ISO date
    duration_sec INTEGER,
    plays INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,             -- 收藏，"高意向但没互动"的人群信号
    completion_rate REAL,                -- 完播率 0-1
    avg_watch_time REAL,                 -- 秒
    profile_visits INTEGER DEFAULT 0,
    new_followers INTEGER DEFAULT 0,
    unfollows INTEGER,
    danmaku_count INTEGER,
    cover_ctr REAL,                      -- 封面点击率 0-1（双列平台才是关键信号）
    bounce_2s_rate REAL,                 -- 2s跳出率 0-1
    fan_conversion_rate REAL,
    high_intent_comments INTEGER DEFAULT 0,  -- 手动标记：问价/问流程等强意向评论数
    high_intent_dms INTEGER DEFAULT 0,
    is_anomaly_period INTEGER DEFAULT 0, -- 落在已知异常期内，自动从 anomaly_periods 算
    notes TEXT,
    raw_data TEXT,                       -- 原始导入字段的 JSON 备份
    -- 只有某一个平台才有的指标（B站投币/三连、小红书曝光量与搜索占比…）进这里。
    -- 规矩：已经在用的列保持是列，新增的平台特有字段一律进 JSON，
    -- 这样表不会慢慢长成六十个稀疏列。
    platform_data TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_posts_account ON posts(account_id, publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_posts_creative ON posts(creative_id);

-- 时序快照。扩散曲线看的是形状/爬升速度，不是终态数字，
-- 所以需要在固定时间点（+1h / +24h / +3d）记一次。
CREATE TABLE IF NOT EXISTS post_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    checked_at TEXT NOT NULL,            -- ISO datetime，你查看的那一刻
    plays INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    saves INTEGER,
    completion_rate REAL,
    profile_visits INTEGER,
    new_followers INTEGER,
    bounce_2s_rate REAL,
    source TEXT DEFAULT 'manual',        -- manual=手动表单 / vision=截图提取
    curve_note TEXT,                     -- 对详情页小时级趋势图形状的定性描述
    platform_data TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_post ON post_snapshots(post_id, checked_at);

CREATE TABLE IF NOT EXISTS anomaly_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id),  -- NULL = 对该 owner 的所有账号生效
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT NOT NULL                 -- 例如 "新号IP+地理标签触发限流"
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 三个可空外键：分析的对象可能是一条 post、一个 creative（跨平台对比，Phase 4）、
    -- 或者整个账号（内容建议/创作者画像）。
    post_id INTEGER REFERENCES posts(id),
    creative_id INTEGER REFERENCES creatives(id),
    account_id INTEGER REFERENCES accounts(id),
    analysis_type TEXT NOT NULL,
    result_json TEXT NOT NULL,
    model_used TEXT,
    input_tokens INTEGER,                -- 成本可见性：这次分析花了多少 token
    output_tokens INTEGER,
    duration_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 账号级指标（数据表现 / 账号诊断 / 手机端数据中心 的截图落这里）。
-- 主页访问、作品搜索量、同行百分位这些只在账号级存在，挂不到单条作品上。
CREATE TABLE IF NOT EXISTS account_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id),
    captured_at TEXT NOT NULL,
    period TEXT,                         -- 统计口径：昨日/近7天/近30天/unknown
    plays INTEGER,
    profile_visits INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    net_followers INTEGER,
    unfollows INTEGER,
    completion_rate REAL,
    search_views INTEGER,                -- 作品搜索（账号级独有）
    cover_ctr REAL,
    danmaku INTEGER,
    peer_percentiles TEXT,               -- JSON：同类创作者百分位
    raw_json TEXT,
    source TEXT DEFAULT 'vision'
);

-- ---- 对话式助手的插槽（Phase 5 才建功能，表结构现在就留好）----
-- 现在建表、以后再建功能，是因为加表最贵的时机是"已经部署、已经有线上数据之后"。
-- 助手要能记住上下文，所以对话必须落库，而不是只活在前端内存里。

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL DEFAULT 'local',
    account_id INTEGER REFERENCES accounts(id),  -- 可空：跨账号的对话
    title TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,                  -- user / assistant / tool
    content TEXT NOT NULL,
    tool_calls TEXT,                     -- JSON：助手调用了哪些分析/查询
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

-- 创作者自己写下的想法。助手要"懂你"，光有数字不够 —— 还得知道你怎么想：
-- 想转的方向、对某条片子的判断、这周觉得推流不对劲。这些平台永远不会给你。
CREATE TABLE IF NOT EXISTS creator_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL DEFAULT 'local',
    account_id INTEGER REFERENCES accounts(id),
    post_id INTEGER REFERENCES posts(id),        -- 可空：挂在某条作品上的想法
    creative_id INTEGER REFERENCES creatives(id),
    body TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 每一次模型调用的账本。分析结果自己也存了 token 数，但那份只覆盖分析：
-- 截图提取不落 analysis_results（它产出的是待确认草稿），而它很可能是花销大头。
-- 只统计分析的话，账单上最大的一块是看不见的。
CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    month TEXT NOT NULL,                 -- YYYY-MM，按月加总用
    provider TEXT NOT NULL,              -- anthropic / gemini
    model TEXT,
    kind TEXT,                           -- analysis / vision_extract
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,                       -- 认不出价格就是 NULL，不猜成 0
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_api_usage_month ON api_usage(month);

-- 记一笔哪些结构性迁移跑过了，迁移脚本靠它保证只跑一次。
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def _adopt_legacy_db():
    """
    v1 的库文件叫 douyin.db，v2 改叫 shiome.db（工具已经不只服务抖音了）。
    只在用默认路径、且新文件还不存在、旧文件在的时候，把旧库**复制**成新库
    —— 复制不是移动：旧文件原地不动，万一迁移出问题还能回去。
    """
    if DB_PATH != _DEFAULT_DB_PATH or DB_PATH.exists() or not _LEGACY_DB_PATH.exists():
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_LEGACY_DB_PATH, DB_PATH)
    print(f"[shiome] 沿用 v1 数据库：{_LEGACY_DB_PATH.name} → {DB_PATH.name}（旧文件保留）")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _adopt_legacy_db()
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    # v1 → v2 结构迁移（幂等，靠 schema_migrations 保证只跑一次）
    from app.migrations import run_migrations
    run_migrations()


def backup_db(keep: int = 10, tag: str | None = None):
    """
    每天第一次启动时把数据库快照备份到 <db目录>/backups/，保留最近 keep 份。
    动机：快照/内容画像是手动录入的、没有其他来源，而数据库文件又住在云同步目录里
    （同步工具抓到写入中途的库文件有损坏风险）。时点快照文件对同步是安全的。
    用 sqlite 官方 backup API 而不是直接 copy，避免拷到写入一半的状态。

    tag 用于结构迁移前的一次性备份（文件名带标记，不参与每日轮转的清理）。
    """
    if not DB_PATH.exists():
        return None
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date
    stamp = date.today().isoformat()
    name = f"{DB_PATH.stem}-{tag}-{stamp}" if tag else f"{DB_PATH.stem}-{stamp}"
    dest = backup_dir / f"{name}{DB_PATH.suffix}"
    if dest.exists():
        return None  # 今天已经备份过（同 tag）
    from app.backups import snapshot
    snapshot(DB_PATH, dest)
    if tag is None:  # 只轮转每日备份，带 tag 的迁移前备份一律保留
        for old in sorted(backup_dir.glob(f"{DB_PATH.stem}-20*{DB_PATH.suffix}"))[:-keep]:
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


def post_falls_in_anomaly(conn, account_id: int | None, publish_date: str) -> bool:
    """异常期可以挂在某个账号上，也可以是 account_id IS NULL（对所有账号生效）。"""
    row = conn.execute(
        """SELECT 1 FROM anomaly_periods
           WHERE ? BETWEEN start_date AND end_date
             AND (account_id IS NULL OR account_id = ?)
           LIMIT 1""",
        (publish_date, account_id),
    ).fetchone()
    return row is not None


def get_snapshots(conn, post_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM post_snapshots WHERE post_id = ? ORDER BY checked_at ASC",
        (post_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_default_account_id(conn, owner_id: str = "local") -> int | None:
    """今天只有一个账号，但调用方一律通过它拿 ID，不写死 1。"""
    row = conn.execute(
        "SELECT id FROM accounts WHERE owner_id = ? ORDER BY id LIMIT 1", (owner_id,)
    ).fetchone()
    return row["id"] if row else None
