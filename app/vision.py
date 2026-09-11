"""
截图 → 结构化草稿（vision 提取层）。

抖音创作者中心没有 API、导出文件只有账号级日播放量两列，所以单视频数据只能从
创作者中心页面截图里来。这里做的是"提取草稿"——绝不直接入库，前端确认/修改后
才通过 /api/vision/save 落库（涉及决策的数字，宁可人工确认一次）。

设计约束（都来自真实截图观察）：
- 用户主要用手机截图，开发者用 PC 网页截图——同样的数据、不同的排版，
  所以 schema 与布局无关：全字段可空、"看见什么提取什么、绝不猜"。
- 私密视频（状态"私密"，指标全是"-"）要标出来，由服务端拒绝入库。
- 单视频详情页带小时级播放趋势图：曲线形状按定性描述提取（不读图上的具体数值，
  图表读数不可靠），给扩散诊断当"目击证词"用。
"""
import io
import os
import json
import time
import base64

from app.analysis.prompts import call_claude_json

# ---- 提取用的模型插槽（与文本分析的 ANALYSIS_MODEL 解耦） ----
# 提取截图是"读字"任务，对视觉能力要求高于文本分析；Haiku 级视觉在密集中文 UI 上不够稳。
# VISION_PROVIDER: anthropic（默认）或 gemini；VISION_MODEL 可覆盖各自默认模型。
VISION_PROVIDER = os.environ.get("VISION_PROVIDER", "anthropic").lower()
_DEFAULT_VISION_MODEL = {
    "anthropic": "claude-sonnet-4-6",   # 刻意高于分析用的 Haiku：读数错了后面全错
    "gemini": "gemini-3.5-flash",
}
VISION_MODEL = os.environ.get("VISION_MODEL") or _DEFAULT_VISION_MODEL.get(VISION_PROVIDER, "claude-sonnet-4-6")

# Claude vision 最佳输入：最长边 ≤1568px。手机原图 2-5MB，压过之后 token 减半以上。
MAX_EDGE = 1568


def prepare_image(file_bytes: bytes, content_type: str | None = None) -> tuple[str, str]:
    """缩到 ≤1568px 最长边并转 JPEG，返回 (media_type, base64)。"""
    from PIL import Image

    im = Image.open(io.BytesIO(file_bytes))
    if max(im.size) > MAX_EDGE:
        ratio = MAX_EDGE / max(im.size)
        im = im.resize((round(im.width * ratio), round(im.height * ratio)), Image.LANCZOS)
    if im.mode != "RGB":  # PNG 的 RGBA/P 转 JPEG 需要先落白底
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A") if im.mode == "RGBA" else None)
        im = bg
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return "image/jpeg", base64.standard_b64encode(buf.getvalue()).decode()


_NULLABLE_INT = {"type": ["integer", "null"]}
_NULLABLE_NUM = {"type": ["number", "null"]}
_NULLABLE_STR = {"type": ["string", "null"]}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "page_type": {
            "type": "string",
            "enum": ["video_detail", "video_list", "account_overview", "account_diagnosis", "unknown"],
            "description": "video_detail=单视频数据详情页；video_list=作品列表（多条视频行）；"
                           "account_overview=账号级数据表现/数据中心；account_diagnosis=账号诊断（雷达图+同行对比）",
        },
        "videos": {
            "type": "array",
            "description": "页面上每条视频一个条目（列表页多条、详情页一条）；账号级页面为空数组",
            "items": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["已发布", "私密", "unknown"],
                               "description": "视频状态徽标；私密视频指标通常全是'-'"},
                    "title": _NULLABLE_STR,
                    "publish_datetime": {"type": ["string", "null"],
                                         "description": "发布时间，尽量转成 YYYY-MM-DD HH:MM；只有日期就 YYYY-MM-DD"},
                    "duration_sec": {**_NULLABLE_INT, "description": "封面角标时长，如 02:56 → 176"},
                    "plays": _NULLABLE_INT,
                    "likes": _NULLABLE_INT,
                    "comments": _NULLABLE_INT,
                    "shares": _NULLABLE_INT,
                    "saves": _NULLABLE_INT,
                    "danmaku_count": _NULLABLE_INT,
                    "completion_rate": {**_NULLABLE_NUM, "description": "完播率，0-1 小数（16.42% → 0.1642）"},
                    "bounce_2s_rate": {**_NULLABLE_NUM, "description": "2s跳出率，0-1 小数"},
                    "avg_watch_time": {**_NULLABLE_NUM, "description": "平均播放时长，秒"},
                    "cover_ctr": {**_NULLABLE_NUM, "description": "封面点击率，0-1 小数"},
                    "new_followers": {**_NULLABLE_INT, "description": "涨粉量"},
                    "unfollows": {**_NULLABLE_INT, "description": "取关量"},
                    "fan_conversion_rate": {**_NULLABLE_NUM, "description": "粉丝转化点击/提及占比，0-1 小数"},
                },
                "required": ["status", "title"],
            },
        },
        "account": {
            "type": ["object", "null"],
            "description": "账号级指标（数据表现/数据中心/账号诊断页面才有；没有就 null）",
            "properties": {
                "period": {"type": ["string", "null"], "enum": ["昨日", "近7天", "近30天", None, "unknown"],
                           "description": "页面选中的统计口径"},
                "plays": _NULLABLE_INT,
                "profile_visits": {**_NULLABLE_INT, "description": "主页访问"},
                "likes": _NULLABLE_INT,
                "comments": _NULLABLE_INT,
                "shares": _NULLABLE_INT,
                "net_followers": {**_NULLABLE_INT, "description": "净增粉丝"},
                "unfollows": {**_NULLABLE_INT, "description": "取关粉丝"},
                "completion_rate": {**_NULLABLE_NUM, "description": "账号级完播率，0-1 小数"},
                "search_views": {**_NULLABLE_INT, "description": "作品搜索（搜索带来的量）"},
                "cover_ctr": _NULLABLE_NUM,
                "danmaku": _NULLABLE_INT,
                "peer_percentiles": {"type": ["object", "null"],
                                     "description": "同类创作者对比，如 {\"播放量\": \"高于99.56%\"}；账号诊断页才有"},
            },
        },
        "curve_observation": {
            "type": ["object", "null"],
            "description": "单视频详情页的播放量趋势图观察（没有图就 null）。只描述形状，不要读图上的具体数值",
            "properties": {
                "visible": {"type": "boolean"},
                "granularity": {"type": "string", "enum": ["每小时", "每天", "累计", "unknown"]},
                "shape_description": {"type": "string",
                                      "description": "一两句话：峰在哪、有没有台阶式跃升/横盘/断崖/二次起量"},
                "pattern_guess": {"type": "string",
                                  "enum": ["健康爬升", "冻结走平", "断崖归零", "自然衰减", "无法判断"]},
            },
            "required": ["visible"],
        },
        "notes": {"type": ["string", "null"],
                  "description": "任何模糊、看不清、需要用户复核的地方；没有就 null"},
    },
    "required": ["page_type", "videos", "account", "curve_observation", "notes"],
}

SYSTEM_PROMPT = """
你是一个数据提取器，从抖音创作者中心的截图里提取结构化数据。截图可能来自手机 App
或 PC 网页——同样的数据、不同的排版，都要能处理，不要假设任何固定布局。

铁律：
- 只提取画面上真实可见的数字。看不见、被遮挡、显示为"-"或空白的字段一律 null，绝不推测。
- 中文数字单位要换算："1.2万"→12000，"2.1亿"→210000000。
- 百分比转成 0-1 小数："16.42%"→0.1642。
- 时长转成秒："02:56"→176，"12秒"→12。
- 作品列表页：每一行视频一个条目，一条都不要漏。
- 状态为"私密"的视频照常列出并标 status="私密"（后续流程会跳过它，但你要如实报告）。
- 单视频详情页的播放趋势图：只做定性描述（形状、峰位、有无台阶/横盘/断崖），
  不要试图从图上读出具体数值——图表读数不可靠。
- 数字大小写混排、千分位、加号（"+33.3%"环比）不要混进绝对值字段；环比涨幅不提取。
- 任何拿不准的地方写进 notes 让用户复核。
""".strip()


USER_PROMPT = "请提取这张创作者中心截图里的全部可见数据。"


def _gemini_schema(node):
    """把 JSON Schema 转成 Gemini response_schema 兼容形态：
    type 数组（["string","null"]）→ 单 type + nullable=True；其余键保留。"""
    if isinstance(node, list):
        return [_gemini_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "type" and isinstance(v, list):
            non_null = [t for t in v if t != "null"]
            out["type"] = non_null[0] if non_null else "string"
            if "null" in v:
                out["nullable"] = True
        else:
            out[k] = _gemini_schema(v)
    # enum 里混进 None 会让 Gemini 校验报错（来自 ["昨日",...,None] 这类写法）
    if "enum" in out and isinstance(out["enum"], list):
        out["enum"] = [e for e in out["enum"] if e is not None]
    return out


def _extract_with_gemini(media_type: str, b64: str) -> dict:
    """Gemini 路线：google-genai SDK + response_schema 强制 JSON。
    错误统一包成与 Claude 路线相同的 {_api_error, retryable} 信封，前端无感知。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"_api_error": "VISION_PROVIDER=gemini 但没设 GEMINI_API_KEY（.env 里加上即可）",
                "retryable": False}
    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        return {"_api_error": "缺少 google-genai 包：pip install google-genai", "retryable": False}

    t0 = time.time()
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                gtypes.Part.from_bytes(data=base64.standard_b64decode(b64), mime_type=media_type),
                USER_PROMPT,
            ],
            config={
                "system_instruction": SYSTEM_PROMPT,
                "response_mime_type": "application/json",
                "response_schema": _gemini_schema(EXTRACTION_SCHEMA),
            },
        )
    except Exception as e:  # google-genai 的异常层级较散，统一按可重试与否粗分
        msg = str(e)
        retryable = any(x in msg for x in ("429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "timeout"))
        return {"_api_error": f"Gemini API 错误：{msg[:300]}", "retryable": retryable}

    um = getattr(resp, "usage_metadata", None)
    meta = {
        "model": VISION_MODEL,
        "input_tokens": getattr(um, "prompt_token_count", None),
        "output_tokens": getattr(um, "candidates_token_count", None),
        "duration_ms": int((time.time() - t0) * 1000),
    }
    from app.database import get_conn
    from app.usage import record_usage
    with get_conn() as conn:
        record_usage(conn, "gemini", VISION_MODEL, "vision_extract",
                     meta["input_tokens"], meta["output_tokens"], meta["duration_ms"])

    try:
        result = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return {"_parse_error": True, "raw_text": str(resp.text)[:2000], "_meta": meta}
    if isinstance(result, dict):
        result["_meta"] = meta
    return result


def extract_screenshot(file_bytes: bytes, content_type: str | None = None) -> dict:
    """一张截图 → 结构化草稿 dict（带 _meta；失败返回 _api_error/_parse_error 信封）。
    提取模型由 VISION_PROVIDER / VISION_MODEL 决定，与文本分析模型解耦。"""
    media_type, b64 = prepare_image(file_bytes, content_type)
    if VISION_PROVIDER == "gemini":
        return _extract_with_gemini(media_type, b64)
    return call_claude_json(
        SYSTEM_PROMPT,
        USER_PROMPT,
        schema=EXTRACTION_SCHEMA,
        images=[(media_type, b64)],
        model=VISION_MODEL,
        kind="vision_extract",
    )
