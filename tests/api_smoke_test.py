"""
数据驱动的 API 冒烟测试：把测试数据放在 tests/fixtures/（api_test_data.json + sample_import.csv），
这个脚本只负责跑通所有 API 连接。想换测试数据就改 fixtures，不用动这里 —— 这就是"数据插槽"。

跑法（必须用一次性测试库，别污染真实 douyin.db）：
    SHIOME_DB_PATH=test_output/2026-07-04_api_smoke_Test.db python -m tests.api_smoke_test

默认只跑"不花钱"的端点（CRUD / CSV 导入 / 快照 / 异常期 / 基线 / 趋势 / 报告）。
分析类端点会调用 Anthropic API（花钱、要 key），默认跳过。确认要测再加：
    SHIOME_DB_PATH=... python -m tests.api_smoke_test --with-analysis
"""
import os
import json
import argparse
import pathlib
import datetime

# 安全闸：只允许写入显式指定的测试库
if not os.environ.get("SHIOME_DB_PATH"):
    raise SystemExit(
        "拒绝执行：请先设置 SHIOME_DB_PATH 指向一次性测试库，避免污染真实 douyin.db。\n"
        "例：SHIOME_DB_PATH=test_output/2026-07-04_api_smoke_Test.db python -m tests.api_smoke_test"
    )

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_conn

FIX = pathlib.Path(__file__).parent / "fixtures"
DATA = json.loads((FIX / "api_test_data.json").read_text(encoding="utf-8"))
CSV_BYTES = (FIX / "sample_import.csv").read_bytes()

results = []  # (ok, name, detail)


def check(name, ok, detail=""):
    results.append((bool(ok), name, "" if ok else str(detail)[:200]))
    print(("  ✅" if ok else "  ❌"), name, ("" if ok else f"-- {str(detail)[:180]}"))


def run(with_analysis: bool):
    created_ids = []
    with TestClient(app) as c:
        # 测试库是一次性的：清空后重播，保证可重复运行
        with get_conn() as conn:
            for t in ("video_snapshots", "analysis_results", "videos", "anomaly_periods"):
                conn.execute(f"DELETE FROM {t}")

        print("\n[1] 异常期")
        for ap_ in DATA["anomaly_periods"]:
            r = c.post("/api/anomaly-periods", json=ap_)
            check("POST /api/anomaly-periods", r.status_code == 200 and "id" in r.json(), r.text)

        print("\n[2] 视频 + 内容画像 + 快照（数据驱动）")
        for entry in DATA["videos"]:
            v = entry["video"]
            r = c.post("/api/videos", json=v)
            ok = r.status_code == 200 and "id" in r.json()
            check(f"POST /api/videos · {v.get('title')}", ok, r.text)
            if not ok:
                continue
            vid = r.json()["id"]
            created_ids.append(vid)
            if entry.get("content_profile"):
                r2 = c.patch(f"/api/videos/{vid}/content-profile", json=entry["content_profile"])
                check(f"PATCH /api/videos/{vid}/content-profile", r2.status_code == 200, r2.text)
            for snap in entry.get("snapshots", []):
                r3 = c.post(f"/api/videos/{vid}/snapshots", json=snap)
                check(f"POST /api/videos/{vid}/snapshots", r3.status_code == 200 and "id" in r3.json(), r3.text)

        print("\n[3] CSV 导入（dummy 创作者中心导出）")
        r = c.post("/api/videos/import", files={"file": ("sample_import.csv", CSV_BYTES, "text/csv")})
        n_csv = r.json().get("inserted", 0) if r.status_code == 200 else 0
        check(f"POST /api/videos/import (导入 {n_csv} 条)", r.status_code == 200 and n_csv > 0, r.text)

        print("\n[4] 读取类端点")
        vids = c.get("/api/videos")
        all_videos = vids.json() if vids.status_code == 200 else []
        check("GET /api/videos", isinstance(all_videos, list) and len(all_videos) > 0, vids.text)
        if created_ids:
            g = c.get(f"/api/videos/{created_ids[0]}")
            check("GET /api/videos/{id}", g.status_code == 200 and g.json().get("platform") == "douyin", g.text)
            s = c.get(f"/api/videos/{created_ids[0]}/snapshots")
            check("GET /api/videos/{id}/snapshots", s.status_code == 200 and isinstance(s.json(), list), s.text)
        ap_list = c.get("/api/anomaly-periods")
        check("GET /api/anomaly-periods", ap_list.status_code == 200 and len(ap_list.json()) > 0, ap_list.text)
        base = c.get("/api/baseline")
        check("GET /api/baseline", base.status_code == 200 and "avg_completion_rate" in base.json(), base.text)
        trend = c.get("/api/trend-data")
        check("GET /api/trend-data", trend.status_code == 200 and isinstance(trend.json(), list), trend.text)
        res = c.get("/api/analyze/results")
        check("GET /api/analyze/results", res.status_code == 200 and isinstance(res.json(), list), res.text)
        idx = c.get("/")
        check("GET / (dashboard)", idx.status_code == 200 and "潮目" in idx.text, "")

        print("\n[5] 报告导出")
        rep = c.get("/api/report")
        check("GET /api/report", rep.status_code == 200 and "潮目 · 账号分析报告" in rep.text, rep.text[:120])
        dl = c.get("/api/report?download=1")
        check("GET /api/report?download=1", dl.status_code == 200 and "attachment" in dl.headers.get("content-disposition", ""),
              dl.headers.get("content-disposition", ""))

        print("\n[6] 异常期自动打标（数据里有落在 2026-03-01~07 内的视频）")
        n_flagged = sum(1 for v in all_videos if v.get("is_anomaly_period"))
        check(f"落在异常期内的视频被自动标记（{n_flagged} 条）", n_flagged >= 1, "期望 >=1 条被标记")

        print("\n[7] 分析类端点（调用 Anthropic API）")
        if with_analysis:
            target = created_ids[0]
            analysis_paths = [
                f"/api/analyze/{target}/enhancement",
                f"/api/analyze/{target}/trend_forecast",
                f"/api/analyze/{target}/pool_diagnosis",
                "/api/analyze/content_ideas",
                "/api/analyze/creator_profile",
            ]
            for path in analysis_paths:
                r = c.post(path)
                body = r.json() if r.status_code == 200 else {}
                ok = r.status_code == 200 and isinstance(body, dict) and not body.get("_parse_error")
                check(f"POST {path}", ok, r.text if r.status_code != 200 else body)
        else:
            print("  ⏭  已跳过（默认不花钱）。确认要测：加 --with-analysis 且设好 ANTHROPIC_API_KEY。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-analysis", action="store_true",
                    help="也测分析类端点（调用 Anthropic API，花钱、要 key）")
    args = ap.parse_args()

    print(f"=== API 冒烟测试 · DB={os.environ['SHIOME_DB_PATH']} · with_analysis={args.with_analysis} ===")
    run(args.with_analysis)

    passed = sum(1 for ok, *_ in results if ok)
    total = len(results)
    print(f"\n=== 结果：{passed}/{total} 通过 ===")

    # 写一份带日期的 _Test 汇总到 test_output（gitignore，不上传）
    out_dir = pathlib.Path("test_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"{datetime.date.today().isoformat()}_api_smoke_Test.md"
    lines = [
        f"# API 冒烟测试汇总 {datetime.date.today().isoformat()}",
        f"- DB: `{os.environ['SHIOME_DB_PATH']}`",
        f"- with_analysis: {args.with_analysis}",
        f"- 通过: **{passed}/{total}**",
        "",
        "| 结果 | 端点/检查 | 备注 |",
        "|---|---|---|",
    ]
    for ok, name, detail in results:
        lines.append(f"| {'✅' if ok else '❌'} | {name} | {detail} |")
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"汇总已写入 {report}")

    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
