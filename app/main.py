import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager

from app.database import init_db, get_conn, video_falls_in_anomaly, get_snapshots, backup_db
from app.models import (
    VideoIn, AnomalyPeriodIn, ContentProfileIn, SnapshotIn, VisionSaveIn,
)
from app.vision import extract_screenshot
from app.ingestion import parse_creator_center_csv
from app.analysis.prompts import compute_baseline
from app.report import build_report_html
from app.analysis.enhancement import analyze_enhancement
from app.analysis.content_ideas import analyze_content_ideas
from app.analysis.trend_forecast import analyze_trend_forecast
from app.analysis.pool_diagnosis import analyze_pool_tier
from app.analysis.creator_profile import analyze_creator_profile


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    backup_db()  # 每天首启快照一份，防 Dropbox 同步弄坏唯一的手录数据
    yield


app = FastAPI(title="潮目 Shiome", lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"


# ---------- 视频数据 ----------

@app.post("/api/videos")
def add_video(video: VideoIn):
    with get_conn() as conn:
        anomaly = video_falls_in_anomaly(conn, video.publish_date)
        cur = conn.execute(
            """
            INSERT INTO videos (platform, douyin_video_id, title, publish_date, duration_sec,
                plays, likes, comments, shares, saves, completion_rate, avg_watch_time,
                profile_visits, new_followers, high_intent_comments, high_intent_dms,
                is_anomaly_period, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                video.platform, video.douyin_video_id, video.title, video.publish_date, video.duration_sec,
                video.plays, video.likes, video.comments, video.shares, video.saves,
                video.completion_rate, video.avg_watch_time, video.profile_visits,
                video.new_followers, video.high_intent_comments, video.high_intent_dms,
                int(anomaly), video.notes,
            ),
        )
        return {"id": cur.lastrowid}


# 数据指标列（CSV 导入和截图提取共用的 upsert 白名单）。
# 内容画像字段（content_summary 等）永远不在这里——那是手动填的，数据同步不许碰。
_METRIC_COLS = [
    "douyin_video_id", "duration_sec", "plays", "likes", "comments", "shares", "saves",
    "completion_rate", "avg_watch_time", "profile_visits", "new_followers",
    "danmaku_count", "cover_ctr", "bounce_2s_rate", "unfollows", "fan_conversion_rate",
    "raw_data",
]


def upsert_video(conn, r: dict) -> tuple[int, str]:
    """
    按 douyin_video_id（有则优先）或 (title, publish_date) 匹配已有视频：
    命中→只更新 r 里带值的指标列（None 不覆盖旧值），没命中→插入。
    返回 (video_id, "inserted"|"updated")。CSV 导入和截图确认入库共用这一条路。
    """
    anomaly = video_falls_in_anomaly(conn, r.get("publish_date", ""))
    existing = None
    if r.get("douyin_video_id"):
        existing = conn.execute(
            "SELECT id FROM videos WHERE douyin_video_id = ?",
            (r["douyin_video_id"],),
        ).fetchone()
    if existing is None:
        existing = conn.execute(
            "SELECT id FROM videos WHERE title = ? AND publish_date = ?",
            (r.get("title"), r.get("publish_date")),
        ).fetchone()

    present = [(c, r[c]) for c in _METRIC_COLS if r.get(c) is not None]
    if existing:
        sets = ", ".join(f"{c} = ?" for c, _ in present)
        sets = (sets + ", " if sets else "") + "is_anomaly_period = ?"
        conn.execute(
            f"UPDATE videos SET {sets} WHERE id = ?",
            [v for _, v in present] + [int(anomaly), existing["id"]],
        )
        return existing["id"], "updated"

    cols = ["platform", "title", "publish_date"] + [c for c, _ in present] + ["is_anomaly_period"]
    vals = ["douyin", r.get("title"), r.get("publish_date")] + [v for _, v in present] + [int(anomaly)]
    cur = conn.execute(
        f"INSERT INTO videos ({','.join(cols)}) VALUES ({','.join('?' * len(vals))})",
        vals,
    )
    return cur.lastrowid, "inserted"


@app.post("/api/videos/import")
async def import_csv(file: UploadFile = File(...)):
    """
    导入创作者中心 CSV。重复导入不再产生重复行：
    有视频ID列时按 douyin_video_id 匹配，否则按 (标题, 发布日期) 匹配；
    命中就只更新数据指标列（不碰手动填的内容画像/备注），没命中才插入。
    单行解析失败会被跳过并逐行报告，不再整个导入失败。
    """
    content = await file.read()
    try:
        records, errors = parse_creator_center_csv(content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    inserted = updated = 0
    with get_conn() as conn:
        for r in records:
            _, action = upsert_video(conn, r)
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
    return {"inserted": inserted, "updated": updated, "errors": errors}


@app.get("/api/videos")
def list_videos(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM videos ORDER BY publish_date DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/videos/{video_id}")
def get_video(video_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not row:
            raise HTTPException(404, "video not found")
        return dict(row)


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int):
    """删掉一条视频及其从属数据（快照、分析结果）。不可恢复——前端要先 confirm。"""
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "video not found")
        n_snaps = conn.execute("DELETE FROM video_snapshots WHERE video_id = ?", (video_id,)).rowcount
        n_results = conn.execute("DELETE FROM analysis_results WHERE video_id = ?", (video_id,)).rowcount
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    return {"deleted": video_id, "snapshots_removed": n_snaps, "results_removed": n_results}


@app.patch("/api/videos/{video_id}/content-profile")
def update_content_profile(video_id: int, profile: ContentProfileIn):
    """
    内容画像字段创作者中心导不出来，靠手动填。只更新传了值的字段，
    没传的字段保留原值（用 COALESCE 而不是覆盖成 NULL）。
    """
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "video not found")
        conn.execute(
            """
            UPDATE videos SET
                content_summary = COALESCE(?, content_summary),
                on_screen_text = COALESCE(?, on_screen_text),
                music = COALESCE(?, music),
                hook_description = COALESCE(?, hook_description),
                content_pillar = COALESCE(?, content_pillar)
            WHERE id = ?
            """,
            (
                profile.content_summary, profile.on_screen_text, profile.music,
                profile.hook_description, profile.content_pillar, video_id,
            ),
        )
        return dict(conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone())


# ---------- 时间快照（流量池定位用） ----------

@app.post("/api/videos/{video_id}/snapshots")
def add_snapshot(video_id: int, snapshot: SnapshotIn):
    from datetime import datetime, timezone

    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "video not found")
        checked_at = snapshot.checked_at or datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO video_snapshots (video_id, checked_at, plays, likes, comments,
                shares, saves, completion_rate, profile_visits, new_followers)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                video_id, checked_at, snapshot.plays, snapshot.likes, snapshot.comments,
                snapshot.shares, snapshot.saves, snapshot.completion_rate,
                snapshot.profile_visits, snapshot.new_followers,
            ),
        )
        return {"id": cur.lastrowid, "checked_at": checked_at}


@app.get("/api/videos/{video_id}/snapshots")
def list_snapshots(video_id: int):
    with get_conn() as conn:
        return get_snapshots(conn, video_id)


# ---------- 异常期 ----------

@app.post("/api/anomaly-periods")
def add_anomaly_period(period: AnomalyPeriodIn):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO anomaly_periods (start_date, end_date, reason) VALUES (?,?,?)",
            (period.start_date, period.end_date, period.reason),
        )
        # 回填已有视频的 is_anomaly_period 标记
        conn.execute(
            "UPDATE videos SET is_anomaly_period = 1 WHERE publish_date BETWEEN ? AND ?",
            (period.start_date, period.end_date),
        )
        return {"id": cur.lastrowid}


@app.get("/api/anomaly-periods")
def list_anomaly_periods():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM anomaly_periods ORDER BY start_date DESC").fetchall()
        return [dict(r) for r in rows]


# ---------- 分析 ----------

@app.post("/api/analyze/{video_id}/enhancement")
def run_enhancement(video_id: int):
    with get_conn() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not video:
            raise HTTPException(404, "video not found")
        baseline = compute_baseline(conn)
    return analyze_enhancement(dict(video), baseline)


@app.post("/api/analyze/{video_id}/trend_forecast")
def run_trend_forecast(video_id: int):
    with get_conn() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not video:
            raise HTTPException(404, "video not found")
        baseline = conn.execute(
            "SELECT * FROM videos WHERE is_anomaly_period = 0 ORDER BY publish_date DESC LIMIT 10"
        ).fetchall()
    return analyze_trend_forecast(dict(video), [dict(r) for r in baseline])


@app.post("/api/analyze/content_ideas")
def run_content_ideas(limit: int = 15):
    with get_conn() as conn:
        recent = conn.execute(
            "SELECT * FROM videos WHERE is_anomaly_period = 0 ORDER BY publish_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        baseline = compute_baseline(conn)
    return analyze_content_ideas([dict(r) for r in recent], baseline)


@app.post("/api/analyze/{video_id}/pool_diagnosis")
def run_pool_diagnosis(video_id: int):
    with get_conn() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not video:
            raise HTTPException(404, "video not found")
        snapshots = get_snapshots(conn, video_id)
        baseline = compute_baseline(conn)
    return analyze_pool_tier(dict(video), snapshots, baseline)


@app.post("/api/analyze/creator_profile")
def run_creator_profile(limit: int = 20):
    with get_conn() as conn:
        recent = conn.execute(
            "SELECT * FROM videos WHERE is_anomaly_period = 0 ORDER BY publish_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return analyze_creator_profile([dict(r) for r in recent])


@app.get("/api/analyze/results")
def get_results(video_id: int | None = None, analysis_type: str | None = None):
    query = "SELECT * FROM analysis_results WHERE 1=1"
    params = []
    if video_id is not None:
        query += " AND video_id = ?"
        params.append(video_id)
    if analysis_type is not None:
        query += " AND analysis_type = ?"
        params.append(analysis_type)
    query += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["result_json"] = json.loads(d["result_json"])
            out.append(d)
        return out


@app.get("/api/trend-data")
def trend_data():
    """给首页趋势图用：按发布日期排序的关键指标 + 异常期标记"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT publish_date, title, plays, completion_rate,
                      CAST(saves AS FLOAT) / NULLIF(plays, 0) as save_rate,
                      new_followers, is_anomaly_period
               FROM videos ORDER BY publish_date ASC"""
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 截图 vision 提取（草稿 → 确认 → 入库） ----------

@app.post("/api/vision/extract")
async def vision_extract(file: UploadFile = File(...)):
    """
    一张创作者中心截图 → 结构化草稿。只提取、不入库——数字必须经人确认。
    失败时返回 {_api_error, retryable} 信封，前端可重试。
    """
    content = await file.read()
    try:
        return extract_screenshot(content, file.content_type)
    except Exception as e:  # 图片本身打不开等本地问题
        raise HTTPException(400, f"图片无法处理：{e}")


@app.post("/api/vision/save")
def vision_save(payload: VisionSaveIn):
    """
    确认面板提交的最终数据入库：
    - videos 逐条 upsert（私密条目服务端直接拒绝——别人看不到的数据不作数）
    - 详情页（video_detail）同时给该视频记一条快照（source='vision'，带曲线观察）
    - account 落 account_metrics
    """
    from datetime import datetime, timezone

    saved, updated, skipped_private, snapshots = 0, 0, 0, 0
    with get_conn() as conn:
        for v in payload.videos:
            if v.status == "私密":
                skipped_private += 1
                continue
            if not v.title or not v.publish_datetime:
                continue  # 没有身份键没法 upsert，前端会要求补全
            publish_date = v.publish_datetime[:10]
            record = v.model_dump(exclude={"status", "publish_datetime"})
            record["publish_date"] = publish_date
            vid, action = upsert_video(conn, record)
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
                    """INSERT INTO video_snapshots
                       (video_id, checked_at, plays, likes, comments, shares, saves,
                        completion_rate, new_followers, bounce_2s_rate, source, curve_note)
                       VALUES (?,?,?,?,?,?,?,?,?,?,'vision',?)""",
                    (vid, checked_at, v.plays, v.likes, v.comments, v.shares, v.saves,
                     v.completion_rate, v.new_followers, v.bounce_2s_rate, curve_note),
                )
                snapshots += 1

        if payload.account is not None:
            a = payload.account
            conn.execute(
                """INSERT INTO account_metrics
                   (captured_at, period, plays, profile_visits, likes, comments, shares,
                    net_followers, unfollows, completion_rate, search_views, cover_ctr,
                    danmaku, peer_percentiles, raw_json, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'vision')""",
                (
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
def list_account_metrics(limit: int = 30):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM account_metrics ORDER BY captured_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 报告导出 ----------

@app.get("/api/baseline")
def get_baseline():
    """账号基线（非异常期均值），给前端指标面板算 Δ 用。"""
    with get_conn() as conn:
        return compute_baseline(conn)


@app.get("/api/report", response_class=HTMLResponse)
def get_report(download: int = 0):
    """生成自包含的账号级 HTML 报告（只用已缓存的分析结果，不触发 API 调用）。
    加 ?download=1 时作为附件下载成单个 .html 文件。"""
    from datetime import datetime
    with get_conn() as conn:
        report_html = build_report_html(conn)
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
