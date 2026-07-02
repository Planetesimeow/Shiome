"""
维度一：这条视频具体该往哪个方向增强。
只看单条视频 vs 账号基线的差值，输出可执行的剪辑/结构调整建议，
不做内容选题、不做流量预测 —— 那是另外两个模块的事。
"""
from app.analysis.prompts import PERSONA_CONTEXT, PLATFORM_MECHANISM_CONTEXT, call_claude_json, save_result

SYSTEM_PROMPT = f"""
你是一个短视频剪辑/结构诊断专家，只负责一件事：
根据这条视频的数据表现 vs 账号历史基线，指出具体该增强的方向。

{PERSONA_CONTEXT}

{PLATFORM_MECHANISM_CONTEXT}

要求：
- 只基于给你的数据下结论，不要编造你没有的信息。
- 完播率和互动深度（评论/转发/收藏）分别对应平台推流的不同阶段，两者表现不一致时
  （比如完播率达标但互动稀薄，或者反过来）要分别指出问题，不要笼统地说"整体一般"。
- 每一条诊断都要能对应到一个具体的、可执行的剪辑/结构改动
  （例如"前3秒完播流失快，说明开场钩子不够，建议把体型反差画面提到前2秒"），
  不要给"多和粉丝互动"这种空话。
- 只返回 JSON，不要任何其他文字，格式：
{{
  "diagnosis": ["数据层面的具体问题，每条一句话"],
  "concrete_edits": ["对应的具体改动建议，每条一句话，要可执行"],
  "what_worked": ["这条视频里表现好于基线、值得保留的地方"]
}}
"""


def analyze_enhancement(video: dict, baseline: dict) -> dict:
    user_content = f"""
账号基线（非异常期均值）：
{baseline}

这条视频的数据：
{video}

请给出增强方向诊断。
"""
    result = call_claude_json(SYSTEM_PROMPT, user_content)
    save_result(video.get("id"), "enhancement", result)
    return result
