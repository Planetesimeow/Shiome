"""
维度一：这条作品具体该往哪个方向增强。
只看单条 vs 账号基线的差值，输出可执行的剪辑/结构调整建议，
不做内容选题、不做流量预测 —— 那是别的模块的事。
"""
from app.analysis.prompts import (
    build_account_context, get_mechanism_context, call_claude_json, save_result,
)


def build_system_prompt(platform: str, account: dict | None) -> str:
    return f"""
你是一个短视频剪辑/结构诊断专家，只负责一件事：
根据这条作品的数据表现 vs 账号历史基线，指出具体该增强的方向。

{build_account_context(account)}

{get_mechanism_context(platform)}

要求：
- 只基于给你的数据下结论，不要编造你没有的信息。
- 完播率和互动深度（评论/转发/收藏）分别对应推流的不同阶段，两者表现不一致时
  （比如完播率达标但互动稀薄，或者反过来）要分别指出问题，不要笼统地说「整体一般」。
- 每一条诊断都要能对应到一个具体的、可执行的剪辑/结构改动
  （例如「前3秒完播流失快，说明开场钩子不够，建议把体型反差画面提到前2秒」），
  不要给「多和粉丝互动」这种空话。
- 基线里的 n 是参与计算的作品条数。n 很小时（比如少于 5），要在结论里说明
  基线本身不稳，别把对基线的偏差当成确定的信号。
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis": {"type": "array", "items": {"type": "string"},
                      "description": "数据层面的具体问题，每条一句话"},
        "concrete_edits": {"type": "array", "items": {"type": "string"},
                           "description": "对应的具体改动建议，每条一句话，要可执行"},
        "what_worked": {"type": "array", "items": {"type": "string"},
                        "description": "这条作品里表现好于基线、值得保留的地方"},
    },
    "required": ["diagnosis", "concrete_edits", "what_worked"],
}


def analyze_enhancement(post: dict, baseline: dict, account: dict | None) -> dict:
    user_content = f"""
账号基线（同账号、非异常期、最近若干条的均值）：
{baseline}

这条作品的数据（creative 字段是内容画像，没有就是还没填）：
{post}

请给出增强方向诊断。
"""
    system_prompt = build_system_prompt(post.get("platform", "douyin"), account)
    result = call_claude_json(system_prompt, user_content, schema=OUTPUT_SCHEMA)
    save_result("enhancement", result, post_id=post.get("id"),
                account_id=post.get("account_id"))
    return result
