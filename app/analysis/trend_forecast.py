"""
维度三：流量趋势推断。

重要前提：平台不对外开放推荐算法数据，这里的「预估」本质上是根据这个账号自己的历史
推流规律做的启发式推断，不是拿到了平台内部信号。prompt 里强制要求带置信度和免责说明。

v2 的一处修正：v1 把「抖音 24 小时内多数已定」这句话写在这个共享 prompt 里。
那是抖音的时间尺度，对搜索长尾型平台（小红书、B站）是错的 —— 现在它回到了
prompts.py 里各平台自己的机制上下文中，这个文件不再假设任何平台的时钟。
"""
from app.analysis.prompts import (
    build_account_context, get_mechanism_context, call_claude_json, save_result,
)


def build_system_prompt(platform: str, account: dict | None) -> str:
    return f"""
你是一个基于历史数据做趋势推断的分析师，只负责一件事：
根据这条作品当前的数据和账号历史的推流规律，推断它接下来的流量走向可能是什么样。

{build_account_context(account)}

{get_mechanism_context(platform)}

严格要求：
- 你没有平台推荐算法的真实数据，只能基于历史模式做推断。绝对不能说得像是确定的预测。
- 上面的平台机制参考只是帮你识别曲线形状像哪种模式，数字不是判据。
- 你拿到的是这条作品的终态数据（不是分时间点的快照），没法真正判断「发布后 N 小时的
  爬升速度」，只能基于终态数字和账号历史做粗略推断 —— 这一点要在 caveat 里如实说明，
  不要假装能看到时序曲线。
- 时间尺度以上面机制参考里写的为准。如果那段说明该平台机制尚未接入，就不要假设任何
  具体的时间窗，直接说明这一点并把置信度压到低。
- 每个判断都要给置信度（低/中/高），并说明置信度低的原因（样本量不够、落在异常期附近等）。
- 明确给出接下来该盯哪几个指标来验证/推翻这个判断。
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "stage_assessment": {"type": "string",
                             "description": "根据现有数据判断这条作品现在处于流量生命周期的哪个阶段"},
        "likely_trajectory": {"type": "string", "description": "接下来可能的走向，用推断的语气"},
        "confidence": {"type": "string", "enum": ["低", "中", "高"]},
        "confidence_reason": {"type": "string", "description": "为什么是这个置信度"},
        "watch_metrics": {"type": "array", "items": {"type": "string"},
                          "description": "接下来该盯的具体指标，用来验证判断"},
        "caveat": {"type": "string",
                   "description": "固定包含：这是基于历史规律的推断，不是平台官方数据"},
    },
    "required": ["stage_assessment", "likely_trajectory", "confidence",
                 "confidence_reason", "watch_metrics", "caveat"],
}


def analyze_trend_forecast(post: dict, historical_pattern: list[dict],
                           account: dict | None) -> dict:
    user_content = f"""
这条作品的当前数据：
{post}

账号近期作品的历史表现（用于识别推流规律）：
{historical_pattern}

请给出流量趋势推断。
"""
    system_prompt = build_system_prompt(post.get("platform", "douyin"), account)
    result = call_claude_json(system_prompt, user_content, schema=OUTPUT_SCHEMA)
    save_result("trend_forecast", result, post_id=post.get("id"),
                account_id=post.get("account_id"))
    return result
