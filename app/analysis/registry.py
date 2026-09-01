"""
分析模块登记表。

一处声明「有哪些分析、各自需要什么、怎么跑」，路由和（Phase 5 的）对话式助手都读它。

为什么要有这层：v1 把五个分析各写死成一个路由，助手要调用它们时得把每个都再包一遍。
登记表让助手可以直接把这些分析当工具列出来、按名字调用 —— 这就是 roadmap 里说的
「给助手留的 socket」，而且它今天就在被路由使用，不是空壳。
"""
from app.analysis.enhancement import analyze_enhancement
from app.analysis.trend_forecast import analyze_trend_forecast
from app.analysis.pool_diagnosis import analyze_diffusion
from app.analysis.content_ideas import analyze_content_ideas
from app.analysis.creator_profile import analyze_creator_profile

POST_SCOPE = "post"        # 针对单条作品
ACCOUNT_SCOPE = "account"  # 针对整个账号


def _run_enhancement(conn, account, post_id):
    from app.analysis.context import get_post_with_creative
    from app.analysis.prompts import compute_baseline
    post = get_post_with_creative(conn, post_id)
    return analyze_enhancement(post, compute_baseline(conn, account["id"]), account)


def _run_trend_forecast(conn, account, post_id):
    from app.analysis.context import get_post_with_creative, recent_posts
    post = get_post_with_creative(conn, post_id)
    return analyze_trend_forecast(post, recent_posts(conn, account["id"], 10), account)


def _run_pool_diagnosis(conn, account, post_id):
    from app.analysis.context import get_post_with_creative
    from app.analysis.prompts import compute_baseline
    from app.database import get_snapshots
    post = get_post_with_creative(conn, post_id)
    return analyze_diffusion(post, get_snapshots(conn, post_id),
                             compute_baseline(conn, account["id"]), account)


def _run_content_ideas(conn, account, limit=15):
    from app.analysis.context import recent_posts
    from app.analysis.prompts import compute_baseline
    return analyze_content_ideas(recent_posts(conn, account["id"], limit),
                                 compute_baseline(conn, account["id"]), account)


def _run_creator_profile(conn, account, limit=20):
    from app.analysis.context import profiled_creatives, recent_posts
    creatives = profiled_creatives(conn, account["id"], limit)
    considered = len(recent_posts(conn, account["id"], limit))
    return analyze_creator_profile(creatives, account, total_considered=considered)


ANALYSES = {
    "enhancement": {
        "label": "增强方向",
        "scope": POST_SCOPE,
        "description": "这条作品 vs 账号基线，具体该往哪个方向改剪辑/结构。",
        "run": _run_enhancement,
    },
    "trend_forecast": {
        "label": "流量预估",
        "scope": POST_SCOPE,
        "description": "基于账号历史推流规律，对这条作品接下来走向的启发式推断（带置信度）。",
        "run": _run_trend_forecast,
    },
    "pool_diagnosis": {
        "label": "扩散诊断",
        "scope": POST_SCOPE,
        "description": "读时序快照的曲线形状：健康爬升 / 冻结 / 断崖 / 自然衰减，以及卡在哪个信号。",
        "run": _run_pool_diagnosis,
    },
    "content_ideas": {
        "label": "内容建议",
        "scope": ACCOUNT_SCOPE,
        "description": "从近期作品里找出跑通的模式，生成新的选题方向（往前看）。",
        "run": _run_content_ideas,
    },
    "creator_profile": {
        "label": "创作者画像",
        "scope": ACCOUNT_SCOPE,
        "description": "按创作物审计现在实际在做什么内容、矩阵结构是否健康（照镜子）。",
        "run": _run_creator_profile,
    },
}


def get_analysis(name: str) -> dict | None:
    return ANALYSES.get(name)


def list_analyses() -> list[dict]:
    """给前端和（将来）助手看的清单，不含函数引用。"""
    return [{"name": k, "label": v["label"], "scope": v["scope"],
             "description": v["description"]} for k, v in ANALYSES.items()]
