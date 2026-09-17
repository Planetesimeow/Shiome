"""
维度二：接下来可能可以增加的内容方向。
看的是最近一批作品的组合表现，找出高于基线的模式，再结合账号人设生成新的选题角度
—— 不做单条作品的剪辑建议。

v2 变化：这个模块以前完全不知道自己在给哪个平台提建议（模块级常量 prompt，
没有任何机制上下文）。现在它拿账号和平台机制 —— 给小红书图文笔记提抖音式的建议
不会报错，只会悄悄给错。
"""
from app.analysis.prompts import (
    build_account_context, get_mechanism_context, SENSITIVE_TOPIC_NOTE,
    call_claude_json, save_result,
)


def build_system_prompt(platform: str, account: dict | None) -> str:
    return f"""
你是一个内容选题策略顾问，只负责一件事：
根据近期作品的组合表现，找出跑通的内容模式，并生成新的选题方向。

{build_account_context(account)}

{get_mechanism_context(platform)}

{SENSITIVE_TOPIC_NOTE}

要求：
- 区分有多条作品支持的稳定方向与单次高表现，给出延续方向和小规模探索方向。
  如果没有给出账号人设或内容描述，就说明信息不足，不要凭空假设已验证的人设公式。
- 按账号自己的成功定义解释观看、涨粉、咨询等结果，不预设其中哪一种优先。
- 选题要贴合这个平台的形态：内容形式、时长、封面/标题的作用在各平台不一样。
  如果该平台机制尚未接入，就不要假设它和抖音一样。
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "high_performing_patterns": {"type": "array", "items": {"type": "string"},
                                     "description": "从数据里看出的、跑通了的内容模式"},
        "new_content_ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "angle": {"type": "string", "description": "选题角度"},
                    "why": {"type": "string", "description": "为什么可能有效"},
                    "risk_note": {"type": ["string", "null"],
                                  "description": "如果涉及敏感表述，这里给更安全的说法；否则填 null"},
                },
                "required": ["angle", "why", "risk_note"],
            },
        },
        "patterns_to_retire": {"type": "array", "items": {"type": "string"},
                               "description": "表现持续低于基线、可以减少投入的内容类型"},
    },
    "required": ["high_performing_patterns", "new_content_ideas", "patterns_to_retire"],
}


def analyze_content_ideas(recent_posts: list[dict], baseline: dict,
                          account: dict | None) -> dict:
    platform = (account or {}).get("platform", "douyin")
    user_content = f"""
账号基线（同账号、非异常期均值）：
{baseline}

最近一批作品的数据（creative 字段是内容画像，没有就是还没填）：
{recent_posts}

请给出内容方向建议。
"""
    result = call_claude_json(build_system_prompt(platform, account),
                              user_content, schema=OUTPUT_SCHEMA)
    save_result("content_ideas", result, account_id=(account or {}).get("id"))
    return result
