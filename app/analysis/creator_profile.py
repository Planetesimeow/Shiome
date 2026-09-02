"""
维度五：内容创作者画像。

跟 content_ideas 的分工：content_ideas 回答「接下来该做什么新内容」（往前看）；
这里回答「现在实际在做什么、矩阵结构怎么样」（照镜子看现状），不给新选题。

v2 变化：读的是 creatives 而不是 posts。一条视频发三个平台，它的钩子/画面文字/配乐
只有一份 —— 内容审计当然应该按创作物来看，否则同一条内容会被数三遍，
矩阵占比会被平台数量放大成假象。
"""
from app.analysis.prompts import (
    build_account_context, get_mechanism_context, call_claude_json, save_result,
)


def build_system_prompt(platform: str, account: dict | None) -> str:
    return f"""
你是一个内容审计分析师，只负责一件事：
根据最近一批创作物的内容描述（不是播放数据本身），总结创作者现在实际在做什么，
并评估内容矩阵结构是否健康。

{build_account_context(account)}

{get_mechanism_context(platform)}

要求：
- 只基于给你的内容描述字段做归纳，缺内容描述的直接跳过，不要编造。
- 矩阵评估要围绕这个账号自己的目标展开（见上面的账号上下文）：
  判断「建立专业感/信任」类和「转化触发」类内容的比例是否合理，
  而不是单纯看内容够不够多元、够不够好玩。
  如果账号没有填写人设和目标，就说明缺这个信息、只做描述性归纳，不下矩阵健康的结论。
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "content_direction_breakdown": {"type": "array", "items": {"type": "string"},
                                        "description": "现在实际在做的几类内容方向，附大致占比或条数"},
        "hook_patterns": {"type": "array", "items": {"type": "string"},
                          "description": "核心抓人点的模式总结，现在反复在用的钩子类型"},
        "text_and_music_style": {"type": "string", "description": "画面文字风格 + 配乐风格的总结"},
        "matrix_assessment": {"type": "string",
                              "description": "内容矩阵结构评估：是否过度集中、信任类与转化类内容比例是否失衡"},
        "matrix_recommendation": {"type": "array", "items": {"type": "string"},
                                  "description": "矩阵结构上的调整建议，是结构性的比重建议，不是具体选题"},
    },
    "required": ["content_direction_breakdown", "hook_patterns", "text_and_music_style",
                 "matrix_assessment", "matrix_recommendation"],
}


def analyze_creator_profile(creatives: list[dict], account: dict | None,
                            total_considered: int | None = None) -> dict:
    platform = (account or {}).get("platform", "douyin")
    total = total_considered if total_considered is not None else len(creatives)
    user_content = f"""
最近这批创作物里，共 {len(creatives)} 条填了内容画像（一共看了 {total} 条）：
{creatives}

注意：这是按「创作物」而不是按「发布」列出的 —— 同一条内容发到多个平台只出现一次。
"""
    result = call_claude_json(build_system_prompt(platform, account),
                              user_content, schema=OUTPUT_SCHEMA)
    save_result("creator_profile", result, account_id=(account or {}).get("id"))
    return result
