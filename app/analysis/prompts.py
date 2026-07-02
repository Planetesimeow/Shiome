"""
三个分析模块（增强方向 / 内容建议 / 流量预估）共用的东西放这里：
账号人设上下文、基线指标计算、调用 Claude 的公共方法。

设计上刻意把三类分析拆成三个独立 prompt/独立调用（而不是一个大 prompt 全干），
原因见 README：单一职责，输出更聚焦，也方便你以后单独迭代某一类分析的 prompt。
"""
import os
import json
from anthropic import Anthropic
from app.database import get_conn

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


MODEL = os.environ.get("ANALYSIS_MODEL", "claude-sonnet-5")

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

# 平台推荐机制参考框架。
# 重要：这是社区反推出来的经验规律，不是官方精确阈值，数字会随时间浮动。
# 用法上只能当"相对判断的参照系"——比如判断这条视频卡在哪个阶段、
# 曲线形状像哪种模式，绝不能当成 pass/fail 的硬性判据去套用，
# 更不能拿泛娱乐大盘的门槛来评判这个账号（本账号目标是精准触达，不是泛娱乐爆量）。
PLATFORM_MECHANISM_CONTEXT = """
平台推荐机制参考（经验框架，用于相对判断，不是精确阈值）：

抖音是分级流量池逐级放量。第一级看点击率/完播率/初始点赞评论比这类"预选赛"指标；
过了第一级之后权重会转向评论深度和分享率，完播率的权重反而下降。所以经常出现
完播率高但互动稀薄的视频卡在中等播放量，完播率一般但评论区有实质讨论的视频反而
冲到更大流量池——完播率是入场券，不是决定后续走势的唯一因素。
持续放量的曲线特征：播放、点赞、评论同步上涨，互动没有随播放量扩大而摊薄。
限流的曲线特征：相比账号历史场均断崖式下跌，且互动同步趴平归零，而不是自然衰减
那种平滑下降。这两种曲线形状差异很大，判断时要分开看，不要混为一谈。

小红书核心是互动分模型，转发、评论、涨粉的权重明显高于点赞。发布后 18-24 小时内
的互动爬升速度，是判断能不能进入更大流量池的关键窗口，看的是这个窗口里的速度而
不是最终总量。持续放量的特征：这个窗口内互动量维持高位。限流的特征：点赞长时间
挂零（不是偏低，是完全没有），这个信号比"低播放量"本身更能说明问题。

两个平台都会根据早期互动人群的构成给账号打标签。如果内容被泛人群大量点开又快速
划走，账号标签会被带偏，之后更难触达精准人群——这类问题在数据表现上容易和"内容
本身一般"混淆，但成因和对策完全不同，分析时要留意区分。
""".strip()


def compute_baseline(conn) -> dict:
    """
    账号级基线指标，只用非异常期的视频计算，避免限流期的数据拉低/污染判断。
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
        FROM videos
        WHERE is_anomaly_period = 0
        """
    ).fetchone()
    return dict(row) if row else {}


def call_claude_json(system: str, user_content: str) -> dict:
    """
    调用 Claude，要求只返回 JSON。解析失败时把原始文本包一层返回，
    方便你在 dashboard 里看到到底是格式问题还是内容问题。
    """
    resp = get_client().messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    try:
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"_parse_error": True, "raw_text": text}


def save_result(video_id: int | None, analysis_type: str, result: dict):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analysis_results (video_id, analysis_type, result_json, model_used) VALUES (?, ?, ?, ?)",
            (video_id, analysis_type, json.dumps(result, ensure_ascii=False), MODEL),
        )
