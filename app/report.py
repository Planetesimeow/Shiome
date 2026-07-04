"""
生成一份自包含的账号级 HTML 报告（暗色 潮目 主题）。

只读取 analysis_results 里**已缓存**的分析结果，不触发任何新的 API 调用（不花钱）。
供 GET /api/report 直接返回，或加 ?download=1 下载成单个 .html 文件。

文本/表格全部服务端渲染成 HTML（不依赖 JS 也能读、能打印）；只有图表用内联 Chart.js
读取内嵌的数据数组来画。配色复用 style.css 的 :root 令牌。
"""
import json
import html
from datetime import datetime

from app.database import get_snapshots
from app.analysis.prompts import compute_baseline, PERSONA_CONTEXT  # noqa: F401 (persona 备用)

ANALYSIS_ORDER = ["enhancement", "trend_forecast", "pool_diagnosis"]
ANALYSIS_LABELS = {
    "enhancement": "增强方向",
    "trend_forecast": "流量预估",
    "pool_diagnosis": "扩散诊断",
    "content_ideas": "内容建议",
    "creator_profile": "创作者画像",
}


# ---------- 小工具 ----------

def _esc(s) -> str:
    return html.escape("" if s is None else str(s))


def _titled_ul(title, items) -> str:
    items = [i for i in (items or []) if i]
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(i)}</li>" for i in items)
    return f"<h3>{_esc(title)}</h3><ul>{lis}</ul>"


def _kv(k, v) -> str:
    if v is None or v == "":
        return ""
    return f'<div class="kv-row"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div></div>'


def _fmt_num(n) -> str:
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return _esc(n)
    if n >= 10000:
        return f"{n / 10000:.1f}w"
    return f"{int(n)}" if n == int(n) else f"{n:.1f}"


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _rate(a, b):
    return (a / b) if b else None


# ---------- 单条分析结果 -> HTML ----------

def _render_result(atype: str, d) -> str:
    if not isinstance(d, dict):
        return '<p class="muted">未运行</p>'
    if d.get("_parse_error"):
        return f'<div class="caveat">解析失败，模型原始输出：</div><pre>{_esc(d.get("raw_text"))}</pre>'

    if atype == "enhancement":
        return (_titled_ul("数据诊断", d.get("diagnosis"))
                + _titled_ul("具体改动建议", d.get("concrete_edits"))
                + _titled_ul("值得保留的地方", d.get("what_worked")))

    if atype == "trend_forecast":
        h = f'<h3>阶段判断</h3><p>{_esc(d.get("stage_assessment"))}</p>'
        h += (f'<h3>可能走向 <span class="confidence">置信度 {_esc(d.get("confidence"))}</span></h3>'
              f'<p>{_esc(d.get("likely_trajectory"))}</p>')
        if d.get("confidence_reason"):
            h += f'<p class="muted">{_esc(d.get("confidence_reason"))}</p>'
        h += _titled_ul("接下来该盯的指标", d.get("watch_metrics"))
        if d.get("caveat"):
            h += f'<div class="caveat">{_esc(d.get("caveat"))}</div>'
        return h

    if atype == "pool_diagnosis":
        shape = d.get("curve_shape") or "—"
        warn = " warn" if any(k in str(shape) for k in ("限流", "断崖", "冻结")) else ""
        h = f'<h3>扩散曲线形状 <span class="confidence">置信度 {_esc(d.get("shape_confidence"))}</span></h3>'
        h += f'<p><span class="badge{warn}">{_esc(shape)}</span></p>'
        h += _kv("扩散阶段", d.get("diffusion_stage"))
        h += _kv("卡点信号", d.get("bottleneck_signal") or "没有明显卡点")
        h += _kv("限流vs衰减", d.get("throttle_vs_decay"))
        h += _titled_ul("推动继续扩散的改动", d.get("unlock_actions"))
        if d.get("caveat"):
            h += f'<div class="caveat">{_esc(d.get("caveat"))}</div>'
        return h

    if atype == "content_ideas":
        h = _titled_ul("跑通的内容模式", d.get("high_performing_patterns"))
        ideas = d.get("new_content_ideas") or []
        if ideas:
            h += "<h3>新选题方向</h3><ul>"
            for idea in ideas:
                if not isinstance(idea, dict):
                    continue
                h += f"<li><strong>{_esc(idea.get('angle'))}</strong> — {_esc(idea.get('why'))}"
                if idea.get("risk_note"):
                    h += f'<br><span class="risk">⚠ {_esc(idea.get("risk_note"))}</span>'
                h += "</li>"
            h += "</ul>"
        h += _titled_ul("可以减少投入的类型", d.get("patterns_to_retire"))
        return h

    if atype == "creator_profile":
        h = _titled_ul("当前内容方向分布", d.get("content_direction_breakdown"))
        h += _titled_ul("钩子模式", d.get("hook_patterns"))
        h += _kv("文字/配乐风格", d.get("text_and_music_style"))
        h += _kv("矩阵评估", d.get("matrix_assessment"))
        h += _titled_ul("矩阵调整建议", d.get("matrix_recommendation"))
        return h

    return '<p class="muted">未知分析类型</p>'


# ---------- 数据聚合 ----------

def _latest_results(conn) -> dict:
    """(video_id, analysis_type) -> 最新一条结果 dict。按时间升序遍历，后写的覆盖，留下最新。"""
    rows = conn.execute(
        "SELECT video_id, analysis_type, result_json FROM analysis_results ORDER BY created_at ASC"
    ).fetchall()
    latest = {}
    for r in rows:
        try:
            latest[(r["video_id"], r["analysis_type"])] = json.loads(r["result_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return latest


def _video_metrics(v: dict, baseline: dict) -> list:
    """返回 [(label, value_str, delta_ratio_or_None, higher_is_better)]，delta 为相对基线的比值差。"""
    save_rate = _rate(v.get("saves"), v.get("plays"))
    v2f = _rate(v.get("new_followers"), v.get("profile_visits"))
    high_intent = (v.get("high_intent_comments") or 0) + (v.get("high_intent_dms") or 0)
    rows = [
        ("完播率", _pct(v.get("completion_rate")), v.get("completion_rate"), baseline.get("avg_completion_rate")),
        ("收藏率", _pct(save_rate), save_rate, baseline.get("avg_save_rate")),
        ("访问→关注", _pct(v2f), v2f, baseline.get("avg_visit_to_follow_rate")),
        ("高意向信号", _fmt_num(high_intent), high_intent, baseline.get("avg_high_intent_signals")),
    ]
    out = []
    for label, vs, val, base in rows:
        delta = None
        if val is not None and base:
            delta = (val - base) / base
        out.append((label, vs, delta))
    return out


def _render_metrics_grid(v: dict, baseline: dict) -> str:
    cells = ""
    for label, vs, delta in _video_metrics(v, baseline):
        d_html = ""
        if delta is not None:
            cls = "up" if delta > 0.02 else "down" if delta < -0.02 else "flat"
            sign = "+" if delta >= 0 else ""
            d_html = f'<div class="delta {cls}">{sign}{delta * 100:.0f}% vs 基线</div>'
        cells += f'<div class="metric"><div class="label">{_esc(label)}</div><div class="value">{_esc(vs)}</div>{d_html}</div>'
    return f'<div class="metrics-grid">{cells}</div>'


# ---------- 主函数 ----------

def build_report_html(conn) -> str:
    videos = [dict(r) for r in conn.execute(
        "SELECT * FROM videos ORDER BY publish_date ASC"
    ).fetchall()]
    baseline = compute_baseline(conn)
    latest = _latest_results(conn)
    snaps = {v["id"]: get_snapshots(conn, v["id"]) for v in videos}
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    n_videos = len(videos)
    n_anomaly = sum(1 for v in videos if v.get("is_anomaly_period"))

    # ---- 图表数据（内嵌，供内联 Chart.js 读取）----
    chart_data = {
        "trend": {
            "labels": [v["publish_date"] for v in videos],
            "plays": [v["plays"] for v in videos],
            "completion": [(v["completion_rate"] * 100) if v.get("completion_rate") is not None else None for v in videos],
            "anomaly": [bool(v["is_anomaly_period"]) for v in videos],
        },
        "diffusion": {},
    }
    for v in videos:
        s = snaps[v["id"]]
        if s:
            chart_data["diffusion"][str(v["id"])] = {
                "labels": [(row.get("checked_at") or "")[:16].replace("T", " ") for row in s],
                "plays": [row.get("plays") for row in s],
                "interaction": [
                    round(((row.get("likes") or 0) + (row.get("comments") or 0)
                           + (row.get("shares") or 0) + (row.get("saves") or 0))
                          / row["plays"] * 100, 2) if row.get("plays") else None
                    for row in s
                ],
            }

    # ---- 概览：视频表 ----
    rows_html = ""
    for v in reversed(videos):  # 表里最近的在上
        flag = '<span class="danger">● 异常期</span>' if v.get("is_anomaly_period") else ""
        rows_html += (
            "<tr>"
            f'<td class="mono">{_esc(v["publish_date"])}</td>'
            f'<td>{_esc(v["title"])}</td>'
            f'<td class="mono num">{_fmt_num(v.get("plays"))}</td>'
            f'<td class="mono num">{_pct(v.get("completion_rate"))}</td>'
            f'<td class="mono num">{_pct(_rate(v.get("saves"), v.get("plays")))}</td>'
            f'<td class="mono num">{_fmt_num(v.get("new_followers"))}</td>'
            f'<td>{flag}</td>'
            "</tr>"
        )
    videos_table = (
        '<table class="data-table"><thead><tr>'
        "<th>日期</th><th>标题</th><th>播放</th><th>完播</th><th>收藏率</th><th>净增粉</th><th></th>"
        "</tr></thead><tbody>" + rows_html + "</tbody></table>"
    )

    # ---- 组合级分析 ----
    portfolio_html = ""
    for atype in ("content_ideas", "creator_profile"):
        res = latest.get((None, atype))
        body = _render_result(atype, res) if res is not None else '<p class="muted">未运行</p>'
        portfolio_html += f'<div class="result-card"><div class="card-tag">{ANALYSIS_LABELS[atype]}</div>{body}</div>'

    # ---- 每条视频区块 ----
    video_sections = ""
    for v in reversed(videos):
        vid = v["id"]
        meta = (f'{_esc(v["publish_date"])} · 播放 {_fmt_num(v.get("plays"))} · '
                f'完播 {_pct(v.get("completion_rate"))}')
        if v.get("is_anomaly_period"):
            meta += ' · <span class="danger">异常期</span>'
        sec = f'<h2 class="video-title">{_esc(v["title"])}</h2><div class="video-meta mono">{meta}</div>'
        sec += _render_metrics_grid(v, baseline)
        if str(vid) in chart_data["diffusion"]:
            sec += (f'<div class="chart-wrap"><div class="chart-title">扩散曲线（快照）</div>'
                    f'<canvas id="diff-{vid}" height="120"></canvas></div>')
        for atype in ANALYSIS_ORDER:
            res = latest.get((vid, atype))
            body = _render_result(atype, res) if res is not None else '<p class="muted">未运行</p>'
            sec += f'<div class="result-card"><div class="card-tag">{ANALYSIS_LABELS[atype]}</div>{body}</div>'
        video_sections += f'<section class="video-block">{sec}</section>'

    body_html = (
        f'<header class="report-header"><h1>潮目 · 账号分析报告</h1>'
        f'<div class="sub mono">生成于 {generated} · 共 {n_videos} 条视频'
        f'（异常期 {n_anomaly} 条）· 数据为已缓存分析，非实时</div></header>'
        f'<section><h2 class="section-h">账号概览</h2>'
        f'<div class="chart-wrap"><div class="chart-title">播放量 & 完播率趋势</div>'
        f'<canvas id="trend" height="90"></canvas>'
        f'<div class="legend-note"><span class="swatch"></span>红色 = 已标记异常期（不计入基线）</div></div>'
        f'{videos_table}</section>'
        f'<section><h2 class="section-h">账号级分析</h2>{portfolio_html}</section>'
        f'<section><h2 class="section-h">逐条视频</h2>{video_sections}</section>'
        f'<footer class="report-footer mono">潮目 Shiome · 本报告仅含已缓存分析结果，'
        f'具体数字为定性参考、非平台真实数据</footer>'
    )

    return (_HTML_HEAD
            + body_html
            + '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>'
            + '<script>const CHART_DATA=' + json.dumps(chart_data, ensure_ascii=False) + ';</script>'
            + _CHART_JS
            + "</body></html>")


# ---------- 静态模板（不含 f-string，避免和 CSS/JS 的花括号打架）----------

_HTML_HEAD = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>潮目 · 账号分析报告</title>
<style>
:root{--bg:#121110;--bg-elevated:#1B1A17;--bg-hover:#232019;--border:#2C2924;
--text:#EAE6DC;--text-muted:#8C877C;--accent:#B9A47E;--danger:#9C4A3C;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
--sans:-apple-system,"PingFang SC","Hiragino Sans","Segoe UI",sans-serif;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);
font-size:14px;line-height:1.6;}
.mono{font-family:var(--mono);}
.num{text-align:right;font-variant-numeric:tabular-nums;}
.muted{color:var(--text-muted);}
.danger{color:var(--danger);}
main,.wrap{max-width:920px;margin:0 auto;padding:0 24px 64px;}
.report-header{max-width:920px;margin:0 auto;padding:40px 24px 24px;border-bottom:1px solid var(--border);}
.report-header h1{font-size:22px;font-weight:600;margin:0 0 8px;letter-spacing:-0.01em;}
.report-header .sub{font-size:12px;color:var(--text-muted);}
section{max-width:920px;margin:0 auto;padding:28px 24px 0;}
.section-h{font-size:13px;text-transform:uppercase;letter-spacing:0.1em;
color:var(--accent);border-bottom:1px solid var(--border);padding-bottom:8px;margin:0 0 18px;}
.chart-wrap{background:var(--bg-elevated);border:1px solid var(--border);border-radius:6px;
padding:16px;margin-bottom:20px;}
.chart-wrap canvas{max-height:240px;}
.chart-title{font-family:var(--mono);font-size:11px;text-transform:uppercase;
letter-spacing:0.08em;color:var(--text-muted);margin-bottom:12px;}
.legend-note{font-family:var(--mono);font-size:10px;color:var(--text-muted);margin-top:8px;}
.legend-note .swatch{display:inline-block;width:10px;height:10px;background:var(--danger);
opacity:0.4;margin-right:4px;vertical-align:middle;}
.data-table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;}
.data-table th{font-family:var(--mono);font-size:10px;text-transform:uppercase;
letter-spacing:0.06em;color:var(--text-muted);text-align:left;padding:8px 10px;
border-bottom:1px solid var(--border);}
.data-table td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top;}
.data-table tbody tr:hover{background:var(--bg-hover);}
.video-block{border-top:1px solid var(--border);padding-top:26px;margin-top:10px;}
.video-title{font-size:16px;font-weight:600;margin:0 0 4px;}
.video-meta{font-size:11px;color:var(--text-muted);margin-bottom:14px;}
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:1px;background:var(--border);border:1px solid var(--border);border-radius:6px;
overflow:hidden;margin-bottom:18px;}
.metric{background:var(--bg-elevated);padding:13px 15px;}
.metric .label{font-family:var(--mono);font-size:10px;letter-spacing:0.08em;
text-transform:uppercase;color:var(--text-muted);}
.metric .value{font-family:var(--mono);font-size:19px;margin-top:5px;font-variant-numeric:tabular-nums;}
.metric .delta{font-family:var(--mono);font-size:11px;margin-top:3px;font-variant-numeric:tabular-nums;}
.metric .delta.up{color:var(--accent);}
.metric .delta.down{color:var(--danger);}
.metric .delta.flat{color:var(--text-muted);}
.result-card{background:var(--bg-elevated);border:1px solid var(--border);border-radius:6px;
padding:20px 22px;margin-bottom:16px;}
.card-tag{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
color:var(--text-muted);margin-bottom:14px;}
.result-card h3{font-size:12px;text-transform:uppercase;letter-spacing:0.08em;
color:var(--accent);margin:18px 0 9px;}
.result-card h3:first-of-type{margin-top:0;}
.result-card p{margin:0 0 12px;}
.result-card ul{margin:0 0 14px;padding-left:18px;}
.result-card li{margin-bottom:7px;line-height:1.55;}
.result-card pre{white-space:pre-wrap;font-family:var(--mono);font-size:11px;color:var(--text-muted);}
.kv-row{display:grid;grid-template-columns:104px 1fr;gap:14px;padding:9px 0;
border-bottom:1px solid var(--border);align-items:baseline;}
.kv-row:last-child{border-bottom:none;}
.kv-row .k{font-family:var(--mono);font-size:11px;letter-spacing:0.05em;
text-transform:uppercase;color:var(--text-muted);}
.kv-row .v{font-size:13px;line-height:1.55;}
.badge{display:inline-block;font-family:var(--mono);font-size:12px;padding:4px 12px;
border-radius:3px;background:var(--bg-hover);border:1px solid var(--accent);color:var(--accent);}
.badge.warn{border-color:var(--danger);color:var(--danger);}
.confidence{display:inline-block;font-family:var(--mono);font-size:10px;padding:2px 8px;
border-radius:10px;border:1px solid var(--border);margin-left:8px;color:var(--text-muted);}
.risk{color:var(--danger);font-size:12px;}
.caveat{font-family:var(--mono);font-size:11px;color:var(--text-muted);
border-top:1px solid var(--border);padding-top:10px;margin-top:10px;}
.report-footer{max-width:920px;margin:40px auto 0;padding:20px 24px 0;font-size:11px;
color:var(--text-muted);border-top:1px solid var(--border);}
@media print{.chart-wrap{break-inside:avoid;}.video-block{break-inside:avoid;}
body{background:#fff;}}
</style></head><body>
"""

_CHART_JS = """<script>
(function(){
  var mono="ui-monospace, monospace", muted="#8C877C", grid="#2C2924",
      accent="#B9A47E", cream="#EAE6DC", danger="#9C4A3C";
  function axis(extra){return Object.assign({ticks:{color:muted,font:{family:mono,size:10}},
      grid:{color:grid}}, extra||{});}
  var t=CHART_DATA.trend;
  if(document.getElementById("trend") && t.labels.length){
    new Chart(document.getElementById("trend"),{
      data:{labels:t.labels,datasets:[
        {type:"bar",label:"播放量",data:t.plays,yAxisID:"y",order:2,
         backgroundColor:t.anomaly.map(function(a){return a?"rgba(156,74,60,0.4)":"rgba(185,164,126,0.55)";})},
        {type:"line",label:"完播率 %",data:t.completion,yAxisID:"y1",order:1,tension:0.2,
         borderColor:cream,borderWidth:1.5,
         pointRadius:t.anomaly.map(function(a){return a?5:2;}),
         pointStyle:t.anomaly.map(function(a){return a?"triangle":"circle";}),
         pointBackgroundColor:t.anomaly.map(function(a){return a?danger:cream;})}
      ]},
      options:{responsive:true,interaction:{mode:"index",intersect:false},
        scales:{y:axis({position:"left"}),y1:axis({position:"right",grid:{display:false}}),x:axis({grid:{display:false}})},
        plugins:{legend:{labels:{color:muted,font:{family:mono,size:11}}}}}
    });
  }
  Object.keys(CHART_DATA.diffusion).forEach(function(vid){
    var d=CHART_DATA.diffusion[vid], el=document.getElementById("diff-"+vid);
    if(!el) return;
    new Chart(el,{data:{labels:d.labels,datasets:[
      {type:"bar",label:"播放量",data:d.plays,yAxisID:"y",order:2,backgroundColor:"rgba(185,164,126,0.55)"},
      {type:"line",label:"互动率 %",data:d.interaction,yAxisID:"y1",order:1,tension:0.3,
       borderColor:cream,borderWidth:1.5,pointRadius:3,pointBackgroundColor:accent}
    ]},
    options:{responsive:true,interaction:{mode:"index",intersect:false},
      scales:{y:axis({position:"left"}),y1:axis({position:"right",grid:{display:false}}),x:axis({grid:{display:false}})},
      plugins:{legend:{labels:{color:muted,font:{family:mono,size:11}}}}}});
  });
})();
</script>
"""
