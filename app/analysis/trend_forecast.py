"""
维度三：平台流量趋势预估。

重要前提：抖音不对外开放推荐算法的数据，这里的"预估"本质上是
根据你自己账号的历史推流规律做的启发式推断，不是拿到了平台内部信号。
prompt 里强制要求带置信度和免责说明，避免看起来像有把握的预测。
"""
from app.analysis.prompts import PERSONA_CONTEXT, get_mechanism_context, call_claude_json, save_result


def build_system_prompt(platform: str) -> str:
    return f"""
你是一个基于历史数据做趋势推断的分析师，只负责一件事：
根据这条视频当前的数据和账号历史的推流规律，推断它接下来的流量走向可能是什么样。

{PERSONA_CONTEXT}

{get_mechanism_context(platform)}

严格要求：
- 你没有平台推荐算法的真实数据，只能基于历史模式做推断。绝对不能说得像是确定的预测。
- 上面的平台机制参考只是帮你识别曲线形状像哪种模式，数字不是判据。
  你现在拿到的是这条视频的终态数据（不是分时间点的曝光/互动快照），
  没法真正判断"发布后N小时的爬升速度"，只能基于终态数字和账号历史做粗略推断，
  这一点要在 caveat 里如实说明，不要假装能看到时序曲线。
- 抖音内容生命周期偏短（天级）：24 小时内多数已定，但 3-7 天存在翻热/回流的可能，
  推断走向时把这个时间尺度考虑进去，不要按更长的长尾周期去推。
- 每个判断都要给置信度（低/中/高），并说明置信度低的原因（比如样本量不够、
  这条视频落在异常期附近等）。
- 明确给出接下来该盯哪几个指标来验证/推翻这个判断。
- 只返回 JSON，不要任何其他文字，格式：
{{
  "stage_assessment": "根据现有数据判断这条视频现在处于流量生命周期的哪个阶段",
  "likely_trajectory": "接下来可能的走向，用推断的语气",
  "confidence": "低/中/高",
  "confidence_reason": "为什么是这个置信度",
  "watch_metrics": ["接下来N小时/天该盯的具体指标，用来验证判断"],
  "caveat": "固定包含：这是基于历史规律的推断，不是平台官方数据"
}}
"""


def analyze_trend_forecast(video: dict, historical_pattern: list[dict]) -> dict:
    user_content = f"""
这条视频的当前数据：
{video}

账号近期视频的历史表现（用于识别推流规律）：
{historical_pattern}

请给出流量趋势推断。
"""
    system_prompt = build_system_prompt(video.get("platform", "douyin"))
    result = call_claude_json(system_prompt, user_content)
    save_result(video.get("id"), "trend_forecast", result)
    return result
