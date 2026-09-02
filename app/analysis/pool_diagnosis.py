"""
维度四：扩散曲线诊断（原「流量池定位」）。

重要纠正：抖音官方已明确没有离散「流量池」这个结构，放量是连续的、多目标概率驱动的过程。
所以这里不判断「在第几级流量池、怎么晋级」，而是读这条作品的扩散曲线形状：
健康爬升、冻结（疑似限流）、断崖归零（疑似审核），还是自然衰减；再据此推断卡在哪个信号。

前提：需要 post_snapshots 时序数据打底。判断曲线形状天生需要看曲线，单个终态数字
回答不了 —— 「发布 24 小时后是这个数」到底是还在爬还是已经收敛，只有时序数据能告诉你。

跟 enhancement 的分工：enhancement 看「整体表现 vs 自己历史基线，该往哪个方向改」；
这里看「这条现在的扩散曲线是什么形状、卡在哪个信号」，更窄、更看时间维度。
"""
from app.analysis.prompts import (
    build_account_context, get_mechanism_context, call_claude_json, save_result,
)


def build_system_prompt(platform: str, account: dict | None) -> str:
    return f"""
你是一个内容扩散曲线诊断分析师，只负责一件事：
根据这条作品的时序快照数据，读出它的扩散曲线形状，推断它现在处于扩散的哪个阶段、
卡在哪个信号，以及要推动它继续扩散，剪辑/结构上可以做哪些改动。

{build_account_context(account)}

{get_mechanism_context(platform)}

要求：
- 不要用「第几级流量池」「晋级门槛」这类离散台阶的说法。判断依据是快照之间的变化趋势：
  爬升有没有出现台阶式跃升、是不是横盘冻结、是不是断崖归零、还是平滑收敛；
  互动率有没有随播放量扩大而摊薄。
- 如果播放量走平，必须明确区分这是「冻结（疑似限流）」还是「自然衰减（平滑收敛）」，
  并给出你据以区分的依据；不要一看量不涨就说限流（限流常被过度归因）。
- 快照数量少（比如只有 1-2 个时间点）的时候，如实降低置信度，不要硬造确定的判断。
- 部分快照带有 curve_note：那是从详情页小时级趋势图截图里提取的曲线形状目击描述
  （一张第 3 天的截图就包含了发布以来的完整早期曲线）。把它当作对数字快照的旁证使用 ——
  两者一致时可以提高置信度；两者矛盾时以数字快照为准，并把矛盾写进判断里。
- 如果上面的机制参考说该平台尚未接入，就不要套用其他平台的曲线形态命名和时间窗，
  如实说明缺少参考框架。
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "curve_shape": {"type": "string",
                        "enum": ["健康爬升", "冻结疑似限流", "断崖归零疑似审核", "自然衰减", "数据不足无法判断"]},
        "shape_confidence": {"type": "string", "enum": ["低", "中", "高"]},
        "diffusion_stage": {"type": "string",
                            "description": "推断现在大概扩散到哪个阶段（核心圈/相邻兴趣圈/泛化人群/已收敛封顶）；看不出就说看不出"},
        "bottleneck_signal": {"type": ["string", "null"],
                              "description": "最可能拖住继续扩散的信号（完播、评论相关度、关注转化、收藏等）；没有明显卡点填 null"},
        "throttle_vs_decay": {"type": ["string", "null"],
                              "description": "如果量走平：这是冻结(疑似限流)还是自然衰减(平滑收敛)，以及区分依据；不适用填 null"},
        "unlock_actions": {"type": "array", "items": {"type": "string"},
                           "description": "针对 bottleneck_signal 的具体、可执行剪辑/结构改动建议"},
        "caveat": {"type": "string",
                   "description": "固定说明：真实算法是黑箱，这是基于快照曲线形状的定性推断，不是平台真实数据"},
    },
    "required": ["curve_shape", "shape_confidence", "diffusion_stage",
                 "bottleneck_signal", "throttle_vs_decay", "unlock_actions", "caveat"],
}


def analyze_diffusion(post: dict, snapshots: list[dict], baseline: dict,
                      account: dict | None) -> dict:
    note = ""
    if len(snapshots) < 2:
        note = (
            "注意：这条作品目前只有不到 2 个时间点的快照，无法判断扩散趋势/曲线形状。"
            "请在 caveat 里明确指出数据不足，shape_confidence 直接给低，"
            "curve_shape 用「数据不足无法判断」。"
        )

    user_content = f"""
{note}

账号基线（同账号、非异常期均值）：
{baseline}

这条作品的当前（终态）数据：
{post}

这条作品的时序快照（按时间顺序排列，越靠后越新）：
{snapshots}

请给出扩散曲线诊断。
"""
    system_prompt = build_system_prompt(post.get("platform", "douyin"), account)
    result = call_claude_json(system_prompt, user_content, schema=OUTPUT_SCHEMA)
    save_result("pool_diagnosis", result, post_id=post.get("id"),
                account_id=post.get("account_id"))
    return result
