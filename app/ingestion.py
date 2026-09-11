"""
作品级 CSV 导入：每行必须包含标题和发布时间，可附作品指标。
兼容常见中英文列名，保留原始列用于复核。账号按日统计的导出不能当作作品导入。
截图走独立的 vision 草稿确认流程，见 docs/capture-guide.md。
"""
import csv
import io
import json
from datetime import datetime

# 我们的字段 -> 可能出现的原始表头（全部小写比较）
COLUMN_ALIASES = {
    "platform_post_id": ["视频id", "作品id", "笔记id", "稿件id", "bv号", "video_id", "note_id"],
    "title": ["视频标题", "标题", "title"],
    "publish_date": ["发布时间", "发布日期", "publish_date", "date"],
    "plays": ["播放量", "播放数", "plays", "views"],
    "likes": ["点赞数", "点赞量", "likes"],
    "comments": ["评论数", "评论量", "comments"],
    "shares": ["分享数", "转发数", "shares"],
    "saves": ["收藏数", "saves", "favorites"],
    "completion_rate": ["完播率", "completion_rate"],
    "avg_watch_time": ["平均播放时长", "人均播放时长", "avg_watch_time"],
    "profile_visits": ["主页访问量", "主页访问次数", "profile_visits"],
    "new_followers": ["涨粉数", "新增粉丝", "new_followers"],
}

NUMERIC_FIELDS = {
    "plays", "likes", "comments", "shares", "saves",
    "profile_visits", "new_followers",
}
PERCENT_FIELDS = {"completion_rate"}
FLOAT_FIELDS = {"avg_watch_time"}  # 秒数，可能带"秒"后缀或 m:ss 格式


def _parse_number(raw: str) -> float:
    """
    宽容地把创作者中心的数字文本转成 float：
    "1,234" / "1.2万" / "3.5w" / "21秒" / "0:21"(分:秒) 都能处理。
    解析不了就抛 ValueError，由上层按行收集错误。
    """
    s = raw.strip().replace(",", "").replace(" ", "")
    if not s:
        raise ValueError("空值")
    if ":" in s:  # m:ss 或 h:mm:ss 时长
        parts = s.split(":")
        if all(p.isdigit() for p in parts):
            sec = 0
            for p in parts:
                sec = sec * 60 + int(p)
            return float(sec)
    # 去掉常见单位后缀
    for suffix in ("秒", "s", "S", "次", "人"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    mult = 1.0
    if s.endswith(("万", "w", "W")):
        mult, s = 1e4, s[:-1]
    elif s.endswith("亿"):
        mult, s = 1e8, s[:-1]
    return float(s) * mult


def _build_header_map(header_row: list[str]) -> dict[str, int]:
    """把 CSV 的表头列名映射到我们的字段名，返回 {字段名: 列下标}"""
    lower_header = [h.strip().lower() for h in header_row]
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower_header:
                mapping[field] = lower_header.index(alias.lower())
                break
    return mapping


def _parse_value(field: str, raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    if field in PERCENT_FIELDS:
        # 支持 "35.2%" 或 "0.352" 两种写法
        if raw.endswith("%"):
            return _parse_number(raw[:-1]) / 100
        val = _parse_number(raw)
        return val / 100 if val > 1 else val
    if field in NUMERIC_FIELDS:
        return int(_parse_number(raw))
    if field in FLOAT_FIELDS:
        return _parse_number(raw)
    if field == "publish_date":
        # 尝试几种常见日期格式，都失败就原样返回，导入时人工修正
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return raw
    return raw


def parse_creator_center_csv(file_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """
    解析创作者中心导出的 CSV，返回 (records, errors)。
    records 的字段名对齐作品指标；未能识别的原始列整体存进 raw_data，不丢数据。
    单行解析失败不再让整个导入报错——记进 errors（带行号和原因），其余行照常导入。
    """
    text = file_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []

    header = rows[0]
    col_map = _build_header_map(header)
    if "title" not in col_map or "publish_date" not in col_map:
        raise ValueError(
            "CSV 里没找到标题/发布时间对应的列。"
            "这里需要每行一条作品的 CSV；只有日期和播放量的账号统计表暂不支持。"
        )

    records, errors = [], []
    for line_no, row in enumerate(rows[1:], start=2):  # 行号按文件计（表头是第1行）
        if not row or not any(row):
            continue
        record, row_errors = {}, []
        for field, idx in col_map.items():
            if idx >= len(row):
                continue
            try:
                record[field] = _parse_value(field, row[idx])
            except (ValueError, TypeError) as e:
                row_errors.append(f"{field}='{row[idx]}' ({e})")
        if not record.get("title") or not record.get("publish_date"):
            errors.append({"line": line_no, "error": "缺标题或发布时间；" + "；".join(row_errors)})
            continue
        if row_errors:
            # 个别字段坏了不整行丢弃：坏字段置空，原始值在 raw_data 里还能找回
            errors.append({"line": line_no, "error": "部分字段未解析：" + "；".join(row_errors)})
        record["raw_data"] = json.dumps(dict(zip(header, row)), ensure_ascii=False)
        records.append(record)
    return records, errors
