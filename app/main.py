import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db, get_conn, video_falls_in_anomaly, get_snapshots
from app.models import VideoIn, AnomalyPeriodIn, ContentProfileIn, SnapshotIn
from app.ingestion import parse_creator_center_csv
from app.analysis.prompts import compute_baseline
from app.analysis.enhancement import analyze_enhancement
from app.analysis.content_ideas import analyze_content_ideas
from app.analysis.trend_forecast import analyze_trend_forecast
from app.analysis.pool_diagnosis import analyze_pool_tier
from app.analysis.creator_profile import analyze_creator_profile

app = FastAPI(title="潮目 Shiome")
STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
def startup():
    init_db()


# ---------- 视频数据 ----------

@app.post("/api/videos")
def add_video(video: VideoIn):
    with get_conn() as conn:
        anomaly = video_falls_in_anomaly(conn, video.publish_date)
        cur = conn.execute(
            """
            INSERT INTO videos (douyin_video_id, title, publish_date, duration_sec,
                plays, likes, comments, shares, saves, completion_rate, avg_watch_time,
                profile_visits, new_followers, high_intent_comments, high_intent_dms,
                is_anomaly_period, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                video.douyin_video_id, video.title, video.publish_date, video.duration_sec,
                video.plays, video.likes, video.comments, video.shares, video.saves,
                video.completion_rate, video.avg_watch_time, video.profile_visits,
                video.new_followers, video.high_intent_comments, video.high_intent_dms,
                int(anomaly), video.notes,
            ),
        )
        return {"id": cur.lastrowid}


@app.post("/api/videos/import")
async def import_csv(file: UploadFile = File(...)):
    content = await file.read()
    try:
        records = parse_creator_center_csv(content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    inserted = 0
    with get_conn() as conn:
        for r in records:
            anomaly = video_falls_in_anomaly(conn, r.get("publish_date", ""))
            conn.execute(
                """
                INSERT INTO videos (title, publish_date, plays, likes, comments, shares,
                    saves, completion_rate, avg_watch_time, profile_visits, new_followers,
                    is_anomaly_period, raw_data)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r.get("title"), r.get("publish_date"), r.get("plays", 0), r.get("likes", 0),
                    r.get("comments", 0), r.get("shares", 0), r.get("saves", 0),
                    r.get("completion_rate"), r.get("avg_watch_time"), r.get("profile_visits", 0),
                    r.get("new_followers", 0), int(anomaly), r.get("raw_data"),
                ),
            )
            inserted += 1
    return {"inserted": inserted}


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


# ---------- 前端 ----------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
