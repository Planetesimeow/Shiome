"""
维度二：接下来可能可以增加的内容方向。
看的是最近一批视频的组合表现，找出高于基线的模式，
再结合账号人设生成新的选题角度 —— 不做单条视频的剪辑建议。
"""
from app.analysis.prompts import PERSONA_CONTEXT, SENSITIVE_TOPIC_NOTE, call_claude_json, save_result

SYSTEM_PROMPT = f"""
你是一个内容选题策略顾问，只负责一件事：
根据近期视频的组合表现，找出跑通的内容模式，并生成新的选题方向。

{PERSONA_CONTEXT}

{SENSITIVE_TOPIC_NOTE}

要求：
- 新选题必须延续账号已验证的人设公式（体态反差钩子 + 系统感数据元素 + 自嘲幽默），
  不要建议偏离人设的泛娱乐内容。
- 目标人群窄且高净值，选题要考虑"能不能筛选出对咨询服务有真实需求的人"，
  而不是单纯追求泛流量。
- 只返回 JSON，不要任何其他文字，格式：
{{
  "high_performing_patterns": ["从数据里看出的、跑通了的内容模式"],
  "new_content_ideas": [
    {{"angle": "选题角度", "why": "为什么可能有效", "risk_note": "如果涉及敏感表述，这里给更安全的说法；否则填 null"}}
  ],
  "patterns_to_retire": ["表现持续低于基线、可以减少投入的内容类型"]
}}
"""


def analyze_content_ideas(recent_videos: list[dict], baseline: dict) -> dict:
    user_content = f"""
账号基线（非异常期均值）：
{baseline}

最近一批视频的数据：
{recent_videos}

请给出内容方向建议。
"""
    result = call_claude_json(SYSTEM_PROMPT, user_content)
    save_result(None, "content_ideas", result)
    return result
