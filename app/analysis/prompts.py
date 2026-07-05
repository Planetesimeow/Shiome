"""
三个分析模块（增强方向 / 内容建议 / 流量预估）共用的东西放这里：
账号人设上下文、基线指标计算、调用 Claude 的公共方法。

设计上刻意把三类分析拆成三个独立 prompt/独立调用（而不是一个大 prompt 全干），
原因见 README：单一职责，输出更聚焦，也方便你以后单独迭代某一类分析的 prompt。
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
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


MODEL = os.environ.get("ANALYSIS_MODEL", "claude-haiku-4-5-20251001")

# 账号人设 —— 这段先写死在这，后面如果人设迭代了在这改就行。
# 分析类 prompt 都会带上这段，保证建议不会跑偏到"泛娱乐涨粉"逻辑上。
PERSONA_CONTEXT = """
账号背景：
- 账号定位：面向在日高净值华人群体的生活方式顾问，内容是信任建立的第一步，
  最终目标是转化为不动产/车辆购置等咨询服务的客户，客户案例再反哺内容。
- 内容公式：体态/体型反差作为钩子 + 热量/宏量营养数据作为"系统感"元素 + 自嘲式幽默作为人设。
- 目标人群体量小、决策周期长、客单价高。账号的"成功"不是泛娱乐意义上的涨粉曲线，
  而是精准触达 + 高转化，粉丝数本身不是核心指标。
- 内容风控：涉及资产、移民身份、大额消费等表述在平台上容易触发限流审查，
  分析时要主动识别这类措辞风险，而不是等被限流才发现。
""".strip()

SENSITIVE_TOPIC_NOTE = (
    "在给内容建议时，凡是涉及资产规模、移民/身份、大额消费金额的具体表述，"
    "都要在 risk_note 字段里标注更安全的替代说法，而不是直接建议原始措辞。"
)

# 平台推荐机制参考框架 —— 按平台分开，用 get_mechanism_context(platform) 取。
# 重要：这是"相对判断的参照系"，不是官方精确阈值，绝不能当 pass/fail 硬判据，
# 更不能拿泛娱乐大盘门槛评判这个账号（本账号目标是精准触达，不是泛娱乐爆量）。
# v1.0.0 只覆盖抖音；小红书 / B站 是预留的接口（socket），到 v2.0.0 再从
# docs/platform-mechanism-findings.md 把结论填进来。
DOUYIN_MECHANISM_CONTEXT = """
抖音推荐机制参考（经验框架，用于相对判断，不是精确阈值，更不是及格线）：

【重要】抖音官方（2025 安全与信任中心）已公开：系统几乎不依赖给内容/用户打显式标签，
而是用神经网络多目标预估每个用户对每条内容产生完播、点赞、评论、转发、关注等行为的概率，
加权后决定推给谁、推多大。官方口径里没有"流量池"这个概念。所以不要用"第几级流量池"
"晋级门槛"这种离散台阶去套——放量是连续的：小批量曝光 → 收集行为信号 → 预估值更新 →
曝光连续放大。社区说的"分级流量池"只是人眼对这个连续过程的近似离散化描述。

判断一条视频，最该做的是读它的"扩散曲线形状"（需要时序快照，单个终态数字看不出形状）：
- 健康爬升：播放稳步上升并出现一到多次台阶式跃升（系统在向更大人群试探），互动率不随
  播放量扩大而摊薄；24-48 小时见顶后缓慢衰减。
- 冻结（疑似限流）：播放在几百量级横盘走平（几乎冻结，不是缓慢上升），互动率正常甚至
  偏高但量不涨。
- 断崖归零（疑似审核拦截 / 判违规）：起量后突然断崖式归零。
- 自然衰减：正常起量后互动率逐轮下滑、系统试探更大人群失败，曲线平滑收敛封顶——注意它
  和"冻结"的手感不同（平滑收敛 vs 冻结走平），别混为一谈。
关键时间窗：首 1 小时（初始人群反馈）、24 小时（多数视频命运已定）、3-7 天（可能翻热/回流）。

信号解读（抖音是单列沉浸流，用户没有"点不点封面"的选择，所以完播/停留权重远高于封面点击率）：
- 完播率是"入场券"不是唯一决定项——多目标模型里没有单一最重要指标，别拿某个百分比当及格线。
- 精准触达信号（本账号真正该看的）：关注转化、主页访问、收藏、评论相关度（评论是不是目标
  人群在提问）、复看。这些更像是对"这条内容触达的人对不对"的投票。
- 泛量噪声信号：点赞、裸播放量。高播放 + 泛互动对精准触达账号价值有限，别被它带偏方向。

限流常被过度归因：多数"我被限流了"其实是自然衰减或内容本身不行。先用上面的曲线形状区分
（冻结 vs 平滑衰减），再下结论；DOU+ 投放被拒可当一次内容"体检"。
""".strip()

# 平台 → 机制参考框架的注册表。加新平台就往这里加一项（v2.0.0）。
_PLATFORM_MECHANISM = {
    "douyin": DOUYIN_MECHANISM_CONTEXT,
}

# 未接入平台的占位说明：不让模型假装了解还没写的平台机制。
_PLATFORM_STUB = (
    "【{platform} 机制尚未接入】本工具 v1.0.0 只覆盖抖音；{platform} 的推荐机制将在 v2.0.0 接入，"
    "参考 docs/platform-mechanism-findings.md 第二部分。在此之前不要假装了解该平台机制，"
    "分析时请明确指出当前缺少该平台机制参考框架，置信度从低起步。"
)


def get_mechanism_context(platform: str | None) -> str:
    """按平台返回推荐机制参考框架。v1.0.0 只有抖音；小红书/B站命中占位说明。"""
    return _PLATFORM_MECHANISM.get((platform or "douyin").lower()) \
        or _PLATFORM_STUB.format(platform=platform)


def compute_baseline(conn, window: int = 20) -> dict:
    """
    账号级基线指标，只用非异常期的视频计算，避免限流期的数据拉低/污染判断。
    只取最近 window 条：基线要代表"当前状态"，全历史平均会把早期摸索阶段的数据
    掺进来，让进步中的账号每条新视频的 Δ 都显得虚高/失真。
    """
    row = conn.execute(
        """
        SELECT
            COUNT(*) as n,
            AVG(completion_rate) as avg_completion_rate,
            AVG(CAST(saves AS FLOAT) / NULLIF(plays, 0)) as avg_save_rate,
            AVG(CAST(profile_visits AS FLOAT) / NULLIF(plays, 0)) as avg_profile_visit_rate,
            AVG(CAST(new_followers AS FLOAT) / NULLIF(profile_visits, 0)) as avg_visit_to_follow_rate,
            AVG(high_intent_comments + high_intent_dms) as avg_high_intent_signals
        FROM (
            SELECT * FROM videos
            WHERE is_anomaly_period = 0
            ORDER BY publish_date DESC
            LIMIT ?
        )
        """,
        (window,),
    ).fetchone()
    return dict(row) if row else {}


def _extract_json(text: str) -> str:
    """从模型输出里尽量把 JSON 抠出来：优先取 ```json``` 代码块里的内容，再收窄到第一个 {
    到最后一个 } 之间。用来容忍模型在 JSON 前后多写了说明文字（Haiku 有时不听"只返回 JSON"，
    会在代码块后面再补一段解读）。"""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end + 1]
    return t


def call_claude_json(system: str, user_content: str, schema: dict | None = None) -> dict:
    """
    调用 Claude 拿结构化结果。

    - 传 schema 时用工具强制 JSON（tool_choice 指定 emit_result），模型只能按 schema
      提交参数，从结构上消灭"JSON 前后多写说明文字"导致的解析失败。
    - API 层错误（key 失效/限流/网络）不再往上抛 500，而是返回
      {"_api_error": 人话, "retryable": bool}，由前端展示并提供重试。
    - 附带 _meta（模型/token 用量/耗时），save_result 会存进库，成本可查。
    """
    kwargs = dict(
        model=MODEL,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user_content}],
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
        "model": MODEL,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "duration_ms": int((time.time() - t0) * 1000),
    }

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


def save_result(video_id: int | None, analysis_type: str, result: dict):
    if result.get("_api_error"):
        return  # API 没打通的调用不落库，避免污染"最新结果"
    meta = result.get("_meta") or {}
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO analysis_results
               (video_id, analysis_type, result_json, model_used,
                input_tokens, output_tokens, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id, analysis_type, json.dumps(result, ensure_ascii=False),
                meta.get("model", MODEL), meta.get("input_tokens"),
                meta.get("output_tokens"), meta.get("duration_ms"),
            ),
        )
