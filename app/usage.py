"""
API 花销的账本，以及每月预算上限。

为什么单独建一张表，而不是从 analysis_results 里加总：截图提取（vision）也花钱，
而且很可能是大头 —— 它每次要传一张图，输入 token 比文本分析高一个量级。
但提取结果不落 analysis_results（它产出的是待确认草稿，不是分析结论）。
只统计分析的话，账单上最大的一块是看不见的。

上限默认不开（不设 SHIOME_MONTHLY_BUDGET_USD 就是不限）：突然拒绝服务比超支更让人困惑。
但花销永远统计、永远可见 —— 部署文档里会建议设一个。
"""
import os
from datetime import datetime, timezone

from app.pricing import cost_usd


def month_key(when: datetime | None = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m")


def budget_limit() -> float | None:
    raw = (os.environ.get("SHIOME_MONTHLY_BUDGET_USD") or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def record_usage(conn, provider: str, model: str | None, kind: str,
                 input_tokens: int | None, output_tokens: int | None,
                 duration_ms: int | None = None):
    """记一次模型调用。认不出价格的（比如 Gemini）成本存 NULL，不猜。"""
    conn.execute(
        """INSERT INTO api_usage
           (created_at, month, provider, model, kind, input_tokens, output_tokens,
            cost_usd, duration_ms)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(), month_key(), provider, model, kind,
         input_tokens, output_tokens, cost_usd(model, input_tokens, output_tokens),
         duration_ms),
    )


def month_spend(conn, month: str | None = None) -> dict:
    """本月花了多少。cost_usd 为 NULL 的调用单独计数，不假装它们是 0 元。"""
    month = month or month_key()
    row = conn.execute(
        """SELECT COALESCE(SUM(cost_usd), 0) AS spent,
                  COUNT(*) AS calls,
                  SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) AS unpriced_calls,
                  COALESCE(SUM(input_tokens), 0) AS input_tokens,
                  COALESCE(SUM(output_tokens), 0) AS output_tokens
           FROM api_usage WHERE month = ?""",
        (month,),
    ).fetchone()
    by_model = [dict(r) for r in conn.execute(
        """SELECT model, provider, COUNT(*) AS calls,
                  COALESCE(SUM(cost_usd), 0) AS spent
           FROM api_usage WHERE month = ?
           GROUP BY model, provider ORDER BY spent DESC""",
        (month,),
    ).fetchall()]

    limit = budget_limit()
    spent = round(row["spent"], 4)
    return {
        "month": month,
        "spent_usd": spent,
        "limit_usd": limit,
        "remaining_usd": round(limit - spent, 4) if limit is not None else None,
        "over_budget": limit is not None and spent >= limit,
        "calls": row["calls"],
        "unpriced_calls": row["unpriced_calls"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "by_model": by_model,
    }


def budget_blocked(conn) -> dict | None:
    """
    超了预算就返回一个跟 API 错误同形状的信封（前端已经会渲染它），没超返回 None。
    刻意在**发起调用之前**检查：事后才发现超支，钱已经花掉了。
    """
    status = month_spend(conn)
    if not status["over_budget"]:
        return None
    return {
        "_api_error": (
            f"本月 API 预算已用完：已花 ${status['spent_usd']:.2f}，"
            f"上限 ${status['limit_usd']:.2f}。"
            f"下个月自动重置；要提高上限就改 .env 里的 SHIOME_MONTHLY_BUDGET_USD。"
        ),
        "retryable": False,
        "_budget": status,
    }
