"""
维度四：流量池定位。

前提：需要 video_snapshots 时序数据打底。判断"现在在哪一级流量池、卡在哪个
指标"天生需要看曲线形状和爬升速度，终态数字回答不了这个问题——只有一个
时间点的数据，跟"发布24小时后是这个数，说明还在爬"和"发布24小时后是这个数，
说明已经死了"是两件完全不同的事，区别只有时序数据能告诉你。

跟 enhancement.py 的分工：enhancement 看的是"整体表现 vs 自己历史基线，
该往哪个方向改"；pool_diagnosis 看的是"现在具体卡在哪一关、要过这一关
最该动哪个指标"，更窄、更聚焦、也更看重时间维度。
"""
from app.analysis.prompts import PERSONA_CONTEXT, PLATFORM_MECHANISM_CONTEXT, call_claude_json, save_result

SYSTEM_PROMPT = f"""
你是一个短视频流量池定位分析师，只负责一件事：
根据这条视频的时序快照数据，推断它现在大概处于哪一级流量池、卡在哪个具体指标，
以及要过这一关，视频剪辑/结构上可以做哪些改动。

{PERSONA_CONTEXT}

{PLATFORM_MECHANISM_CONTEXT}

要求：
- 平台的分级门槛数字不是精确值，不要机械套用某个百分比当成及格线。
  主要判断依据是快照之间的变化趋势——爬升速度有没有放缓、互动占播放量的比例
  有没有随播放量扩大而摊薄，平台机制参考只用来定性判断"曲线形状像哪种模式"。
- 快照数量少（比如只有1-2个时间点）的时候，如实降低置信度，
  不要硬造一个听起来很确定的判断。
- 只返回 JSON，不要任何其他文字，格式：
{{
  "current_tier": "推测现在大概在哪一级流量池，用文字描述；看不出来就说看不出来",
  "tier_confidence": "低/中/高",
  "blocking_metric": "卡住晋级的具体指标；没有明显卡点就填 null",
  "current_vs_target": "这个指标现在大概什么水平，大概要到什么水平才可能突破",
  "unlock_actions": ["针对 blocking_metric 的具体剪辑/结构改动建议，要可执行"],
  "caveat": "固定说明：这是基于快照数据和经验框架的推断，不是平台真实算法数据"
}}
"""


def analyze_pool_tier(video: dict, snapshots: list[dict], baseline: dict) -> dict:
    note = ""
    if len(snapshots) < 2:
        note = (
            "注意：这条视频目前只有不到2个时间点的快照，无法判断爬升趋势。"
            "建议在 caveat 里明确指出数据不足，置信度直接给低。"
        )

    user_content = f"""
{note}

账号基线（非异常期均值）：
{baseline}

这条视频的当前（终态）数据：
{video}

这条视频的时序快照（按时间顺序排列，越靠后越新）：
{snapshots}

请给出流量池定位判断。
"""
    result = call_claude_json(SYSTEM_PROMPT, user_content)
    save_result(video.get("id"), "pool_diagnosis", result)
    return result
