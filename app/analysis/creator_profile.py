"""
维度五：内容创作者画像。

跟 content_ideas.py 的分工：content_ideas 回答"接下来该做什么新内容"，是往前看
的选题建议，靠的是表现数据（哪类内容表现好）；creator_profile 回答"现在实际
在做什么、矩阵结构怎么样"，是照镜子看现状的审计，不给新选题，只描述现状、
评估矩阵结构是否健康。两个可以互相当输入喂数据，但职责不重叠。

前提：需要 videos 表里的内容画像字段打底（content_summary / on_screen_text /
music / hook_description / content_pillar）。这些字段创作者中心导不出来，
只能手动录入——网页表单或者你自己维护一份 md 都行，最终要落到这几个字段里。
"""
from app.analysis.prompts import PERSONA_CONTEXT, call_claude_json, save_result

SYSTEM_PROMPT = f"""
你是一个内容审计分析师，只负责一件事：
根据最近一批视频的内容描述（不是播放数据本身），总结创作者现在实际在做什么，
并评估内容矩阵结构是否健康。

{PERSONA_CONTEXT}

要求：
- 只基于给你的内容描述字段做归纳，缺内容描述的视频直接跳过，不要编造。
- 矩阵评估要围绕账号的实际目标展开：内容是信任建立的第一步，最终要转化成
  咨询服务的客户。判断现在的内容里，"建立专业感/信任"类和"转化触发"类
  （比如引导私信、引导进群）的比例是否合理，而不是单纯看内容够不够多元、
  够不够好玩。
- 只返回 JSON，不要任何其他文字，格式：
{{
  "content_direction_breakdown": ["现在实际在做的几类内容方向，附大致占比或条数"],
  "hook_patterns": ["核心抓人点的模式总结，现在反复在用的钩子类型"],
  "text_and_music_style": "画面文字风格 + 配乐风格的总结",
  "matrix_assessment": "内容矩阵结构评估：是否过度集中、信任类与转化类内容比例是否失衡",
  "matrix_recommendation": ["矩阵结构上的调整建议，是结构性的比重建议，不是具体选题"]
}}
"""


def analyze_creator_profile(recent_videos: list[dict]) -> dict:
    profiled = [
        v for v in recent_videos
        if v.get("content_summary") or v.get("hook_description")
    ]
    user_content = f"""
最近一批视频里，共 {len(profiled)} 条有内容画像数据（总共取了 {len(recent_videos)} 条视频）：
{profiled}
"""
    result = call_claude_json(SYSTEM_PROMPT, user_content)
    save_result(None, "creator_profile", result)
    return result
