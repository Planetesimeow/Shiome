"""
FastAPI 路由层。

v2 的 API 是破坏性重命名过的：/api/videos* → /api/posts*，另外多了 accounts / creatives
/ creator-notes / duplicate-candidates。没有保留旧路径的兼容别名 —— 唯一的调用方就是
我们自己的前端，留着两套名字只会让新来的人不知道该用哪个。
"""
import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from contextlib import asynccontextmanager, closing, suppress

from app import __version__
from app import database
from app.backups import daily_backups, snapshot
from app.auth import (
    AuthConfig, LoginThrottle, SESSION_COOKIE, is_loopback, make_session,
    read_session, verify_password,
)
from app.database import (
    init_db, get_conn, post_falls_in_anomaly, get_snapshots, backup_db,
    get_default_account_id,
)
from app.models import (
    PostIn, AccountIn, AccountPatch, CreativeIn, CreativePatch,
    AnomalyPeriodIn, SnapshotIn, VisionSaveIn, MergeIn, CreatorNoteIn, LoginIn,
)
from app.dedupe import find_duplicate_candidates, merge_posts, title_similarity, \
    TITLE_SIMILARITY_THRESHOLD
from app.vision import extract_screenshot
from app.ingestion import parse_creator_center_csv
from app.analysis.prompts import compute_baseline, get_account
from app.analysis.registry import ANALYSES, list_analyses, POST_SCOPE, ACCOUNT_SCOPE
from app.report import build_report_html
from app.usage import budget_blocked, month_spend


AUTH = AuthConfig()
THROTTLE = LoginThrottle()

# 不需要登录就能访问的路径。刻意列得很短：
# 登录页本身、登录接口、问「我登录了吗」、以及版本号（排查问题时要能拿到）。
PUBLIC_PATHS = {"/login", "/api/auth/login", "/api/auth/status", "/api/version",
                "/favicon.ico", "/healthz"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    AUTH.validate()
    init_db()          # 建表 + 跑结构迁移（v1→v2 会自己先备份）
    backup_db()        # 每天首启快照一份，防云同步弄坏唯一的手录数据
    if not AUTH.configured:
        print("[shiome] 未配置鉴权：只接受来自本机的请求。"
              "要放到公网上，先设 SHIOME_PASSWORD_HASH（用 python -m scripts.set_password 生成）。")
    elif AUTH.secret_derived:
        print("[shiome] 提示：没设 SHIOME_SECRET_KEY，会话密钥从口令哈希派生。"
              "改口令会让所有人重新登录一次。")
    backup_task = asyncio.create_task(daily_backups())
    try:
        yield
    finally:
        backup_task.cancel()
        with suppress(asyncio.CancelledError):
            await backup_task


app = FastAPI(title="潮目 Shiome", version=__version__, lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"


def _client_key(request: Request) -> str:
    return (request.client.host if request.client else "") or "unknown"


def _authenticated_owner(request: Request) -> str | None:
    """Bearer token（脚本/手机快捷指令）优先，其次是浏览器的签名 cookie。"""
    header = request.headers.get("authorization", "")
    if AUTH.api_token and header.lower().startswith("bearer "):
        import hmac as _hmac
        if _hmac.compare_digest(header[7:].strip(), AUTH.api_token):
            return AUTH.owner_id
    session = read_session(request.cookies.get(SESSION_COOKIE), AUTH.secret)
    return session.get("sub") if session else None


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static/") or path in PUBLIC_PATHS:
        return await call_next(request)

    if not AUTH.configured:
        # 没配鉴权 = 只给本机用。不是「先跑起来再说」的宽松默认，
        # 而是让「忘了配就上公网」这条路直接走不通。
        if is_loopback(_client_key(request)):
            request.state.owner_id = AUTH.owner_id
            return await call_next(request)
        return JSONResponse(
            {"detail": "这个实例还没有配置鉴权，因此只接受本机访问。"
                       "要远程使用，先设置 SHIOME_PASSWORD_HASH。"},
            status_code=403,
        )

    owner = _authenticated_owner(request)
    if owner is None:
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "需要登录"}, status_code=401)

    request.state.owner_id = owner
    return await call_next(request)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# ---------- 登录 ----------

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request, response: Response):
    """口令换一个签名 cookie。失败按来源 IP 限速，挡在线暴力猜口令。"""
    if not AUTH.configured:
        raise HTTPException(400, "这个实例没有配置口令，本机访问无需登录。")
    key = _client_key(request)
    if not THROTTLE.check(key):
        raise HTTPException(429, "登录尝试过于频繁，请过一会儿再试。")
    if not AUTH.password_hash or not verify_password(payload.password, AUTH.password_hash):
        THROTTLE.record_failure(key)
        raise HTTPException(401, "口令不对。")
    THROTTLE.reset(key)
    token = make_session(AUTH.owner_id, AUTH.secret, AUTH.session_days)
    response.set_cookie(
        SESSION_COOKIE, token, max_age=AUTH.session_days * 86400,
        httponly=True, samesite="lax", secure=AUTH.production or request.url.scheme == "https",
    )
    return {"ok": True, "owner_id": AUTH.owner_id}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/status")
def auth_status(request: Request):
    """前端据此决定显不显示登录框。不泄露口令是否设置之外的任何信息。"""
    return {
        "configured": AUTH.configured,
        "authenticated": _authenticated_owner(request) is not None
        or (not AUTH.configured and is_loopback(_client_key(request))),
    }


@app.get("/api/version")
def get_version_public():
    """公开：排查问题时不用先登录才能知道对面跑的是哪一版。"""
    return {"version": __version__}


@app.get("/healthz")
def health():
    """Readiness without returning account data or creating a missing database."""
    try:
        with closing(sqlite3.connect(database.DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()
    except sqlite3.Error:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}


@app.get("/api/backup")
def download_backup():
    """Authenticated, fresh database export for storage away from the server."""
    temp = tempfile.TemporaryDirectory(prefix="shiome-export-")
    name = "shiome-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".db"
    path = Path(temp.name) / name
    try:
        snapshot(database.DB_PATH, path)
    except Exception:
        temp.cleanup()
        raise
    return FileResponse(path, media_type="application/octet-stream", filename=name,
                        background=BackgroundTask(temp.cleanup))


def _resolve_account(conn, account_id: int | None) -> dict:
    """没指定账号就用默认账号。所有查询都经过它，不在代码里写死 id=1。"""
    if account_id is None:
        account_id = get_default_account_id(conn)
    account = get_account(conn, account_id)
    if not account:
        raise HTTPException(404, "account not found（还没有账号，先 POST /api/accounts）")
    return account


# ---------- 账号 ----------

@app.get("/api/accounts")
def list_accounts(owner_id: str = "local"):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE owner_id = ? ORDER BY id", (owner_id,)
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/accounts")
def create_account(account: AccountIn, owner_id: str = "local"):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO accounts (owner_id, platform, handle, display_name, persona, goal_note)
               VALUES (?,?,?,?,?,?)""",
            (owner_id, account.platform, account.handle, account.display_name,
             account.persona, account.goal_note),
        )
        return {"id": cur.lastrowid}


@app.patch("/api/accounts/{account_id}")
def update_account(account_id: int, patch: AccountPatch):
    fields = patch.model_dump(exclude_unset=True)
    with get_conn() as conn:
        if not get_account(conn, account_id):
            raise HTTPException(404, "account not found")
        if fields:
            conn.execute(
                f"UPDATE accounts SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                list(fields.values()) + [account_id],
            )
        return dict(conn.execute("SELECT * FROM accounts WHERE id = ?",
                                 (account_id,)).fetchone())


# ---------- 创作物（内容画像住这里，一条内容发多平台只填一次）----------

@app.get("/api/creatives")
def list_creatives(owner_id: str = "local", limit: int = 100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM creatives WHERE owner_id = ? ORDER BY id DESC LIMIT ?",
            (owner_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/creatives")
def create_creative(creative: CreativeIn, owner_id: str = "local"):
    with get_conn() as conn:
        return {"id": _insert_creative(conn, creative.model_dump(), owner_id)}


def _insert_creative(conn, data: dict, owner_id: str = "local") -> int:
    cols = [k for k, v in data.items() if v is not None]
    cur = conn.execute(
        f"INSERT INTO creatives (owner_id, {','.join(cols)}) "
        f"VALUES (?, {','.join('?' * len(cols))})",
        [owner_id] + [data[c] for c in cols],
    )
    return cur.lastrowid


@app.get("/api/creatives/{creative_id}")
def get_creative(creative_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM creatives WHERE id = ?", (creative_id,)).fetchone()
        if not row:
            raise HTTPException(404, "creative not found")
        return dict(row)


@app.patch("/api/creatives/{creative_id}")
def update_creative(creative_id: int, patch: CreativePatch):
    """
    只更新显式传了的字段。传空字符串就是真的清空 —— 表单显示的一直是库里的当前值，
    「清空后保存」就该真的清空。
    """
    fields = patch.model_dump(exclude_unset=True)
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM creatives WHERE id = ?", (creative_id,)).fetchone():
            raise HTTPException(404, "creative not found")
        if fields:
            conn.execute(
                f"UPDATE creatives SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                list(fields.values()) + [creative_id],
            )
        return dict(conn.execute("SELECT * FROM creatives WHERE id = ?",
                                 (creative_id,)).fetchone())


# ---------- 作品（发布）----------

# 数据指标列：CSV 导入和截图提取共用的 upsert 白名单。
# 内容画像字段不在这里，也不可能在 —— v2 之后它们根本不在 posts 表上，
# 数据同步在结构上就碰不到手填的内容。
_METRIC_COLS = [
    "platform_post_id", "duration_sec", "plays", "likes", "comments", "shares", "saves",
    "completion_rate", "avg_watch_time", "profile_visits", "new_followers",
    "danmaku_count", "cover_ctr", "bounce_2s_rate", "unfollows", "fan_conversion_rate",
    "raw_data", "platform_data",
]


def _find_existing_post(conn, account_id: int, r: dict) -> int | None:
    """
    身份判定，按可靠性从高到低：
    1. 平台侧作品 ID（有就一锤定音）
    2. 同账号 + 同发布日期 + 标题高度相似 —— 列表页标题是截断的、OCR 还会读错字，
       v1 用精确匹配，于是同一条视频进了两行。
    """
    if r.get("platform_post_id"):
        row = conn.execute(
            "SELECT id FROM posts WHERE account_id = ? AND platform_post_id = ?",
            (account_id, r["platform_post_id"]),
        ).fetchone()
        if row:
            return row["id"]
    rows = conn.execute(
        "SELECT id, title FROM posts WHERE account_id = ? AND publish_date = ?",
        (account_id, r.get("publish_date")),
    ).fetchall()
    best, best_sim = None, 0.0
    for row in rows:
        sim = title_similarity(r.get("title"), row["title"])
        if sim > best_sim:
            best, best_sim = row["id"], sim
    return best if best_sim >= TITLE_SIMILARITY_THRESHOLD else None


def upsert_post(conn, r: dict, account_id: int, platform: str = "douyin") -> tuple[int, str]:
    """命中已有作品就只更新带值的指标列（None 不覆盖旧值），没命中才插入。"""
    anomaly = post_falls_in_anomaly(conn, account_id, r.get("publish_date", ""))
    if isinstance(r.get("platform_data"), dict):
        r = {**r, "platform_data": json.dumps(r["platform_data"], ensure_ascii=False)}
    existing = _find_existing_post(conn, account_id, r)
    present = [(c, r[c]) for c in _METRIC_COLS if r.get(c) is not None]

    if existing:
        sets = ", ".join(f"{c} = ?" for c, _ in present)
        sets = (sets + ", " if sets else "") + "is_anomaly_period = ?"
        conn.execute(
            f"UPDATE posts SET {sets} WHERE id = ?",
            [v for _, v in present] + [int(anomaly), existing],
        )
        return existing, "updated"

    cols = ["account_id", "platform", "title", "publish_date"] + [c for c, _ in present] \
        + ["is_anomaly_period"]
    vals = [account_id, platform, r.get("title"), r.get("publish_date")] \
        + [v for _, v in present] + [int(anomaly)]
    cur = conn.execute(
        f"INSERT INTO posts ({','.join(cols)}) VALUES ({','.join('?' * len(vals))})", vals
    )
    return cur.lastrowid, "inserted"


@app.post("/api/posts")
def add_post(post: PostIn):
    with get_conn() as conn:
        account = _resolve_account(conn, post.account_id)
        data = post.model_dump()
        data.pop("account_id", None)
        creative_id = data.pop("creative_id", None)
        anomaly = post_falls_in_anomaly(conn, account["id"], post.publish_date)
        if isinstance(data.get("platform_data"), dict):
            data["platform_data"] = json.dumps(data["platform_data"], ensure_ascii=False)
        cols = [k for k, v in data.items() if v is not None]
        cur = conn.execute(
            f"INSERT INTO posts (account_id, creative_id, platform, is_anomaly_period, "
            f"{','.join(cols)}) VALUES (?,?,?,?,{','.join('?' * len(cols))})",
            [account["id"], creative_id, account["platform"], int(anomaly)]
            + [data[c] for c in cols],
        )
        return {"id": cur.lastrowid}


@app.post("/api/posts/import")
async def import_csv(file: UploadFile = File(...), account_id: int | None = None):
    """
    导入创作者中心 CSV。重复导入不会产生重复行：有作品 ID 就按它匹配，
    否则按 同账号+同发布日期+标题高度相似 匹配。单行解析失败会被跳过并逐行报告。
    """
    content = await file.read()
    try:
        records, errors = parse_creator_center_csv(content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    inserted = updated = 0
    with get_conn() as conn:
        account = _resolve_account(conn, account_id)
        for r in records:
            _, action = upsert_post(conn, r, account["id"], account["platform"])
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
    return {"inserted": inserted, "updated": updated, "errors": errors}


# 注意：这两个字面量路由必须写在 /api/posts/{post_id} 前面，否则会被当成 post_id 去解析。
@app.get("/api/posts/duplicate-candidates")
def duplicate_candidates(account_id: int | None = None):
    """
    疑似重复的作品分组。只给候选和判断依据，**不自动合并** ——
    合并是破坏性的，跟截图入库一样必须人点头。
    """
    with get_conn() as conn:
        acct = account_id if account_id is not None else get_default_account_id(conn)
        return find_duplicate_candidates(conn, acct)


@app.post("/api/posts/merge")
def merge_duplicate_posts(payload: MergeIn):
    """确认合并。底稿取字段最全的那条，其余行的非空值补进来，快照并过来去重。"""
    with get_conn() as conn:
        try:
            return merge_posts(conn, payload.post_ids)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/api/posts")
def list_posts(account_id: int | None = None, limit: int = 50):
    with get_conn() as conn:
        acct = account_id if account_id is not None else get_default_account_id(conn)
        rows = conn.execute(
            "SELECT * FROM posts WHERE account_id = ? ORDER BY publish_date DESC LIMIT ?",
            (acct, limit),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/posts/{post_id}")
def get_post(post_id: int):
    from app.analysis.context import get_post_with_creative
    with get_conn() as conn:
        post = get_post_with_creative(conn, post_id)
        if not post:
            raise HTTPException(404, "post not found")
        return post


@app.delete("/api/posts/{post_id}")
def delete_post(post_id: int):
    """删掉一条作品及其从属数据（快照、分析结果）。不可恢复——前端要先 confirm。
    注意不动 creative：同一个创作物可能还发在别的平台上。"""
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone():
            raise HTTPException(404, "post not found")
        n_snaps = conn.execute("DELETE FROM post_snapshots WHERE post_id = ?", (post_id,)).rowcount
        n_results = conn.execute("DELETE FROM analysis_results WHERE post_id = ?", (post_id,)).rowcount
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    return {"deleted": post_id, "snapshots_removed": n_snaps, "results_removed": n_results}


@app.patch("/api/posts/{post_id}/content-profile")
def update_post_content_profile(post_id: int, profile: CreativePatch):
    """
    便捷入口：给这条作品填内容画像。它实际写的是 creative —— 没有就建一个并挂上。
    一条内容发到多个平台时，改任何一条 post 的画像都是在改同一个 creative。
    """
    fields = profile.model_dump(exclude_unset=True)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(404, "post not found")
        post = dict(row)
        creative_id = post.get("creative_id")
        if creative_id is None:
            data = {k: v for k, v in fields.items()}
            data.setdefault("label", (post.get("title") or "")[:40])
            data.setdefault("duration_sec", post.get("duration_sec"))
            creative_id = _insert_creative(conn, data)
            conn.execute("UPDATE posts SET creative_id = ? WHERE id = ?",
                         (creative_id, post_id))
        elif fields:
            conn.execute(
                f"UPDATE creatives SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                list(fields.values()) + [creative_id],
            )
        return dict(conn.execute("SELECT * FROM creatives WHERE id = ?",
                                 (creative_id,)).fetchone())


# ---------- 时序快照（扩散诊断用）----------

@app.post("/api/posts/{post_id}/snapshots")
def add_snapshot(post_id: int, snapshot: SnapshotIn):
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone():
            raise HTTPException(404, "post not found")
        checked_at = snapshot.checked_at or datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO post_snapshots (post_id, checked_at, plays, likes, comments,
                   shares, saves, completion_rate, profile_visits, new_followers,
                   bounce_2s_rate)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (post_id, checked_at, snapshot.plays, snapshot.likes, snapshot.comments,
             snapshot.shares, snapshot.saves, snapshot.completion_rate,
             snapshot.profile_visits, snapshot.new_followers, snapshot.bounce_2s_rate),
        )
        return {"id": cur.lastrowid, "checked_at": checked_at}


@app.get("/api/posts/{post_id}/snapshots")
def list_snapshots(post_id: int):
    with get_conn() as conn:
        return get_snapshots(conn, post_id)


# ---------- 创作者笔记（助手要懂你，光有数字不够）----------

@app.post("/api/creator-notes")
def add_creator_note(note: CreatorNoteIn, owner_id: str = "local"):
    with get_conn() as conn:
        account_id = note.account_id or get_default_account_id(conn)
        cur = conn.execute(
            """INSERT INTO creator_notes (owner_id, account_id, post_id, creative_id, body)
               VALUES (?,?,?,?,?)""",
            (owner_id, account_id, note.post_id, note.creative_id, note.body),
        )
        return {"id": cur.lastrowid}


@app.get("/api/creator-notes")
def list_creator_notes(account_id: int | None = None, post_id: int | None = None,
                       limit: int = 50):
    from app.analysis.context import creator_notes
    with get_conn() as conn:
        acct = account_id if account_id is not None else get_default_account_id(conn)
        return creator_notes(conn, acct, post_id=post_id, limit=limit)


# ---------- 异常期 ----------

@app.post("/api/anomaly-periods")
def add_anomaly_period(period: AnomalyPeriodIn):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO anomaly_periods (account_id, start_date, end_date, reason) VALUES (?,?,?,?)",
            (period.account_id, period.start_date, period.end_date, period.reason),
        )
        # 回填已有作品的 is_anomaly_period 标记
        if period.account_id is None:
            conn.execute(
                "UPDATE posts SET is_anomaly_period = 1 WHERE publish_date BETWEEN ? AND ?",
                (period.start_date, period.end_date),
            )
        else:
            conn.execute(
                """UPDATE posts SET is_anomaly_period = 1
                   WHERE account_id = ? AND publish_date BETWEEN ? AND ?""",
                (period.account_id, period.start_date, period.end_date),
            )
        return {"id": cur.lastrowid}


@app.get("/api/anomaly-periods")
def list_anomaly_periods():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM anomaly_periods ORDER BY start_date DESC").fetchall()
        return [dict(r) for r in rows]


# ---------- 分析 ----------

@app.get("/api/analyses")
def get_analyses():
    """有哪些分析可跑。前端据此渲染 tab；Phase 5 的助手据此把它们当工具列出来。"""
    return list_analyses()


@app.post("/api/analyze/posts/{post_id}/{analysis_type}")
def run_post_analysis(post_id: int, analysis_type: str):
    spec = ANALYSES.get(analysis_type)
    if not spec or spec["scope"] != POST_SCOPE:
        raise HTTPException(404, f"没有这个单条作品分析：{analysis_type}")
    with get_conn() as conn:
        if (blocked := budget_blocked(conn)) is not None:
            return blocked
        row = conn.execute("SELECT account_id FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(404, "post not found")
        account = _resolve_account(conn, row["account_id"])
        return spec["run"](conn, account, post_id)


@app.post("/api/analyze/account/{analysis_type}")
def run_account_analysis(analysis_type: str, account_id: int | None = None,
                         limit: int = 20):
    spec = ANALYSES.get(analysis_type)
    if not spec or spec["scope"] != ACCOUNT_SCOPE:
        raise HTTPException(404, f"没有这个账号级分析：{analysis_type}")
    with get_conn() as conn:
        if (blocked := budget_blocked(conn)) is not None:
            return blocked
        account = _resolve_account(conn, account_id)
        return spec["run"](conn, account, limit)


@app.get("/api/analyze/results")
def get_results(post_id: int | None = None, account_id: int | None = None,
                analysis_type: str | None = None):
    query = "SELECT * FROM analysis_results WHERE 1=1"
    params: list = []
    if post_id is not None:
        query += " AND post_id = ?"
        params.append(post_id)
    if account_id is not None:
        query += " AND account_id = ?"
        params.append(account_id)
    if analysis_type is not None:
        query += " AND analysis_type = ?"
        params.append(analysis_type)
    query += " ORDER BY created_at DESC"
    with get_conn() as conn:
        out = []
        for r in conn.execute(query, params).fetchall():
            d = dict(r)
            d["result_json"] = json.loads(d["result_json"])
            out.append(d)
        return out


@app.get("/api/usage")
def get_usage(month: str | None = None):
    """本月 API 花销。没设上限时 limit_usd 为 null —— 统计照常，只是不拦。"""
    with get_conn() as conn:
        return month_spend(conn, month)


@app.get("/api/baseline")
def get_baseline(account_id: int | None = None):
    """账号基线（同账号、非异常期均值），给前端指标面板算 Δ 用。"""
    with get_conn() as conn:
        account = _resolve_account(conn, account_id)
        return compute_baseline(conn, account["id"])


@app.get("/api/trend-data")
def trend_data(account_id: int | None = None):
    """首页趋势图：按发布日期排序的关键指标 + 异常期标记"""
    with get_conn() as conn:
        acct = account_id if account_id is not None else get_default_account_id(conn)
        rows = conn.execute(
            """SELECT publish_date, title, plays, completion_rate,
                      CAST(saves AS FLOAT) / NULLIF(plays, 0) as save_rate,
                      new_followers, is_anomaly_period
               FROM posts WHERE account_id = ? ORDER BY publish_date ASC""",
            (acct,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 截图 vision 提取（草稿 → 确认 → 入库） ----------

@app.post("/api/vision/extract")
async def vision_extract(file: UploadFile = File(...)):
    """一张创作者中心截图 → 结构化草稿。只提取、不入库——数字必须经人确认。"""
    with get_conn() as conn:
        if (blocked := budget_blocked(conn)) is not None:
            return blocked
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "截图超过 10 MB，请缩小后再上传。")
    try:
        return await run_in_threadpool(extract_screenshot, content, file.content_type)
    except Exception as e:  # 图片本身打不开等本地问题
        raise HTTPException(400, f"图片无法处理：{e}")


@app.post("/api/vision/save")
def vision_save(payload: VisionSaveIn):
    """
    确认面板提交的最终数据入库：
    - posts 逐条 upsert（私密条目服务端直接拒绝——别人看不到的数据不作数）
    - 详情页同时给该作品记一条快照（source='vision'，带曲线观察）
    - 账号级数据落 account_metrics
    """
    saved, updated, skipped_private, snapshots = 0, 0, 0, 0
    with get_conn() as conn:
        account = _resolve_account(conn, payload.account_id)
        for v in payload.videos:
            if v.status == "私密":
                skipped_private += 1
                continue
            if not v.title or not v.publish_datetime:
                continue  # 没有身份键没法 upsert，前端会要求补全
            record = v.model_dump(exclude={"status", "publish_datetime"})
            record["publish_date"] = v.publish_datetime[:10]
            pid, action = upsert_post(conn, record, account["id"], account["platform"])
            if action == "inserted":
                saved += 1
            else:
                updated += 1

            if payload.page_type == "video_detail":
                checked_at = payload.checked_at or datetime.now(timezone.utc).isoformat()
                curve_note = None
                co = payload.curve_observation
                if co and co.visible:
                    curve_note = (f"[{co.granularity or 'unknown'}] "
                                  f"{co.shape_description or ''}"
                                  f"（形态初判：{co.pattern_guess or '无'}）")
                conn.execute(
                    """INSERT INTO post_snapshots
                       (post_id, checked_at, plays, likes, comments, shares, saves,
                        completion_rate, new_followers, bounce_2s_rate, source, curve_note)
                       VALUES (?,?,?,?,?,?,?,?,?,?,'vision',?)""",
                    (pid, checked_at, v.plays, v.likes, v.comments, v.shares, v.saves,
                     v.completion_rate, v.new_followers, v.bounce_2s_rate, curve_note),
                )
                snapshots += 1

        if payload.account is not None:
            a = payload.account
            conn.execute(
                """INSERT INTO account_metrics
                   (account_id, captured_at, period, plays, profile_visits, likes,
                    comments, shares, net_followers, unfollows, completion_rate,
                    search_views, cover_ctr, danmaku, peer_percentiles, raw_json, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'vision')""",
                (
                    account["id"],
                    payload.checked_at or datetime.now(timezone.utc).isoformat(),
                    a.period, a.plays, a.profile_visits, a.likes, a.comments, a.shares,
                    a.net_followers, a.unfollows, a.completion_rate, a.search_views,
                    a.cover_ctr, a.danmaku,
                    json.dumps(a.peer_percentiles, ensure_ascii=False) if a.peer_percentiles else None,
                    a.model_dump_json(),
                ),
            )

    return {"inserted": saved, "updated": updated, "snapshots": snapshots,
            "skipped_private": skipped_private,
            "account_saved": payload.account is not None}


@app.get("/api/account-metrics")
def list_account_metrics(account_id: int | None = None, limit: int = 30):
    with get_conn() as conn:
        acct = account_id if account_id is not None else get_default_account_id(conn)
        rows = conn.execute(
            "SELECT * FROM account_metrics WHERE account_id = ? ORDER BY captured_at DESC LIMIT ?",
            (acct, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 报告导出 ----------

@app.get("/api/report", response_class=HTMLResponse)
def get_report(account_id: int | None = None, download: int = 0):
    """自包含的账号级 HTML 报告（只用已缓存的分析结果，不触发 API 调用）。
    加 ?download=1 作为附件下载成单个 .html 文件。"""
    with get_conn() as conn:
        account = _resolve_account(conn, account_id)
        report_html = build_report_html(conn, account)
    headers = {}
    if download:
        fname = f"shiome_report_{datetime.now():%Y-%m-%d}.html"
        headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return HTMLResponse(content=report_html, headers=headers)


# ---------- 前端 ----------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
