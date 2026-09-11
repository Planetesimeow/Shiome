"""
所有分析模块共用的东西：账号上下文、平台机制参考框架、基线计算、调 Claude 的公共方法。

v2 的两处重要变化：
1. **人设不再写死在源码里。** v1 把一个具体账号的人设常量写在这个文件中间；
   工具一旦服务多个账号（哪怕只是同一个人的三个平台），那就是错的。
   现在人设是 accounts.persona 的数据，按 account_id 取。
2. **基线按账号（因而按平台）隔离。** v1 的 compute_baseline 对表里最近 20 条求平均，
   不分平台。抖音完播率、B站完播率、和根本没有完播率的小红书图文笔记被平均成一个数，
   而 dashboard 上每个"对基线 Δ"都由它算出来 —— 这类 bug 不会报错，只会给出自信的错误结论。

分析刻意拆成多个独立 prompt/独立调用（而不是一个大 prompt 全干）：单一职责，输出更聚焦，
也方便单独迭代某一类分析而不影响其他。
"""
import os
import re
import json
import time
from anthropic import Anthropic, APIError, APIConnectionError, APIStatusError, RateLimitError
from app.database import get_conn

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=get_api_key())
    return _client


def get_api_key() -> str | None:
    """
    单独一个函数而不是内联 os.environ —— 将来支持多用户时，
    每个用户自带 key 只要改这里，不用动任何调用点。
    """
    return os.environ.get("ANTHROPIC_API_KEY")


MODEL = os.environ.get("ANALYSIS_MODEL", "claude-haiku-4-5-20251001")

SENSITIVE_TOPIC_NOTE = (
    "在给内容建议时，凡是涉及资产规模、移民/身份、大额消费金额的具体表述，"
    "都要在 risk_note 字段里标注更安全的替代说法，而不是直接建议原始措辞。"
)

_NO_PERSONA_NOTE = (
    "【这个账号还没有填写人设】不要假设它的定位、目标人群或转化目标。"
    "分析时只依据数据本身，并在结论里指出：补上账号人设后判断会更准。"
)


def get_account(conn, account_id: int | None) -> dict | None:
    if account_id is None:
        return None
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return dict(row) if row else None


def build_account_context(account: dict | None) -> str:
    """
    账号上下文段落。人设为空时如实说明，绝不沿用别的账号的人设 ——
    悄悄套用错误的定位，比没有定位更糟。
    """
    if not account:
        return _NO_PERSONA_NOTE
    lines = [f"账号：{account.get('display_name') or '未命名'}"
             f"（平台：{account.get('platform')}）"]
    persona = (account.get("persona") or "").strip()
    lines.append(persona if persona else _NO_PERSONA_NOTE)
    if account.get("goal_note"):
        lines.append(f"这个账号怎么算成功：{account['goal_note']}")
    return "\n".join(lines)


# 平台推荐机制参考框架 —— 按平台分开，用 get_mechanism_context(platform) 取。
# 重要：这是"相对判断的参照系"，不是官方精确阈值，绝不能当 pass/fail 硬判据，
# 根据账号自己的目标解释指标。历史研究不直接作为当前平台规则。
DOUYIN_MECHANISM_CONTEXT = """
抖音作品分析纪律（观察框架，不是官方算法或固定晋级门槛）：
- 先按账号的成功定义解释结果。目标是稳定内容方向、观看和涨粉时，分别比较播放、观看质量、
  新增关注及播放到关注的转化，寻找多条作品重复出现的模式；不要把高播放一概视为噪声。
  只有账号明确以咨询或商业转化为目标时，才把高意向评论、私信等作为主要成功标准。
- 对比同账号、相近内容形态与时长、相近发布后观察时点的数据。样本少或观察口径不一致，
  就说明限制；不能用发布一天的作品与发布一个月的累计值直接评判内容优劣。
- 缺失指标不是零。账号近7天或30天汇总不能当作单条作品指标，净增粉不能当作新增关注。
  没有受众、流量来源或内容描述，就不能编造触达人群、推荐渠道、开场画面或流失原因。
- 先描述快照的增长、横盘、增速变化，再提出可验证的解释。区分累计播放与分时新增播放：
  新增播放归零不等于累计播放归零。曲线形状本身不能证明限流、审核、固定推流阶段或权重。
  不用固定播放量、完播率或“24小时定生死”作及格线，不承诺下一条能获得多少播放。
- 给出下一次可执行的内容实验与复查指标，区分已观察的事实、可能解释和待验证假设。
""".strip()

_PLATFORM_MECHANISM = {
    "douyin": DOUYIN_MECHANISM_CONTEXT,
}

# 未接入平台的占位说明：不让模型假装了解还没写的平台机制。
# 这段是这个项目最该守住的纪律之一 —— 见 docs/roadmap-v2.md。
_PLATFORM_STUB = (
    "【{platform} 机制尚未接入】本工具目前只覆盖抖音；{platform} 的推荐机制参考框架"
    "还没有写（计划见 docs/roadmap-v2.md，研究底稿见 docs/platform-mechanism-findings.md）。"
    "在此之前：不要假装了解该平台机制，不要套用其他平台的时间窗、指标权重或推荐阶段。"
    "分析时明确指出当前缺少该平台的参考框架，置信度从低起步。"
)


def get_mechanism_context(platform: str | None) -> str:
    """按平台返回推荐机制参考框架。没接入的平台命中占位说明。"""
    return _PLATFORM_MECHANISM.get((platform or "douyin").lower()) \
        or _PLATFORM_STUB.format(platform=platform)


def compute_baseline(conn, account_id: int, window: int = 20) -> dict:
    """
    账号级基线指标。两个限定：
    - 只算这一个账号（因而只算一个平台）：跨平台平均完播率没有意义。
    - 只用非异常期的作品，避免限流期数据污染判断。
    - 只取最近 window 条：基线要代表"当前状态"，全历史平均会把早期摸索阶段掺进来，
      让进步中的账号每条新作品的 Δ 都显得虚高。
    """
    row = conn.execute(
        """
        SELECT
            COUNT(*) as n,
            AVG(plays) as avg_plays,
            AVG(new_followers) as avg_new_followers,
            AVG(CAST(new_followers AS FLOAT) / NULLIF(plays, 0)) as avg_play_to_follow_rate,
            AVG(completion_rate) as avg_completion_rate,
            AVG(CAST(saves AS FLOAT) / NULLIF(plays, 0)) as avg_save_rate,
            AVG(CAST(profile_visits AS FLOAT) / NULLIF(plays, 0)) as avg_profile_visit_rate,
            AVG(CAST(new_followers AS FLOAT) / NULLIF(profile_visits, 0)) as avg_visit_to_follow_rate,
            AVG(high_intent_comments + high_intent_dms) as avg_high_intent_signals
        FROM (
            SELECT * FROM posts
            WHERE account_id = ? AND is_anomaly_period = 0
            ORDER BY publish_date DESC
            LIMIT ?
        )
        """,
        (account_id, window),
    ).fetchone()
    return dict(row) if row else {}


def _extract_json(text: str) -> str:
    """从模型输出里尽量把 JSON 抠出来：优先取 ```json``` 代码块，再收窄到第一个 {
    到最后一个 } 之间。用来容忍模型在 JSON 前后多写了说明文字。"""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end + 1]
    return t


def call_claude_json(system: str, user_content: str, schema: dict | None = None,
                     images: list[tuple[str, str]] | None = None,
                     model: str | None = None, kind: str = "analysis") -> dict:
    """
    调用 Claude 拿结构化结果。

    - 传 schema 时用工具强制 JSON（tool_choice 指定 emit_result），模型只能按 schema
      提交参数，从结构上消灭"JSON 前后多写说明文字"导致的解析失败。
    - 传 images（[(media_type, base64), ...]）时走 vision：图片块在前、文字在后。
    - API 层错误（key 失效/限流/网络）不往上抛 500，而是返回
      {"_api_error": 人话, "retryable": bool}，由前端展示并提供重试。
    - 附带 _meta（模型/token 用量/耗时），save_result 会存进库，成本可查。
    """
    if images:
        content = [
            {"type": "image",
             "source": {"type": "base64", "media_type": mt, "data": b64}}
            for mt, b64 in images
        ] + [{"type": "text", "text": user_content}]
    else:
        content = user_content
    use_model = model or MODEL
    kwargs = dict(
        model=use_model,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    if schema is not None:
        kwargs["tools"] = [{
            "name": "emit_result",
            "description": "提交结构化分析结果。所有字段含义见参数说明。",
            "input_schema": schema,
        }]
        kwargs["tool_choice"] = {"type": "tool", "name": "emit_result"}

    t0 = time.time()
    try:
        resp = get_client().messages.create(**kwargs)
    except (APIConnectionError, RateLimitError) as e:
        return {"_api_error": f"网络/限流问题（可重试）：{e}", "retryable": True}
    except APIStatusError as e:
        retryable = e.status_code >= 500
        return {"_api_error": f"API 返回 {e.status_code}：{e.message}", "retryable": retryable}
    except APIError as e:
        return {"_api_error": str(e), "retryable": False}

    meta = {
        "model": use_model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "duration_ms": int((time.time() - t0) * 1000),
    }
    # 记账。分析结果之后可能被覆盖或删掉，但钱已经花了 —— 账本要独立留存。
    from app.usage import record_usage
    with get_conn() as conn:
        record_usage(conn, "anthropic", use_model, kind, meta["input_tokens"],
                     meta["output_tokens"], meta["duration_ms"])

    result = None
    if schema is not None:
        for block in resp.content:
            if block.type == "tool_use" and block.name == "emit_result":
                result = block.input
                break
    if result is None:
        text = "".join(block.text for block in resp.content if block.type == "text")
        try:
            result = json.loads(_extract_json(text))
        except json.JSONDecodeError:
            return {"_parse_error": True, "raw_text": text, "_meta": meta}
    if isinstance(result, dict):
        result["_meta"] = meta
    return result


def save_result(analysis_type: str, result: dict, post_id: int | None = None,
                account_id: int | None = None, creative_id: int | None = None):
    """分析结果落库。三个可空外键决定这条结果说的是谁：一条作品 / 一个创作物 / 整个账号。"""
    if result.get("_api_error"):
        return  # API 没打通的调用不落库，避免污染"最新结果"
    meta = result.get("_meta") or {}
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO analysis_results
               (post_id, creative_id, account_id, analysis_type, result_json,
                model_used, input_tokens, output_tokens, duration_ms)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                post_id, creative_id, account_id, analysis_type,
                json.dumps(result, ensure_ascii=False),
                meta.get("model", MODEL), meta.get("input_tokens"),
                meta.get("output_tokens"), meta.get("duration_ms"),
            ),
        )
