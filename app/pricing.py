"""
把 token 用量换算成钱。

价目表是**快照**，不是实时的（下面标了日期）。所以：
- 认不出来的模型返回 None，而不是猜一个价格 —— 一个编出来的成本数字比没有数字更糟，
  因为它看起来像是可信的。
- 可以用 SHIOME_PRICE_<模型名> 覆盖某个模型的价格，不用改代码。
- 带日期后缀的模型 ID（claude-haiku-4-5-20251001）按最长前缀匹配到基础型号。
"""
import os

# 单位：美元 / 每百万 token，(输入, 输出)
# 来源：Anthropic 官方价目，快照于 2026-06-24。
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

PRICES_SNAPSHOT_DATE = "2026-06-24"


def _env_override(model: str) -> tuple[float, float] | None:
    """SHIOME_PRICE_CLAUDE_OPUS_5="5,25" 这样覆盖。价目表过期时不用改代码。"""
    key = "SHIOME_PRICE_" + model.upper().replace("-", "_").replace(".", "_")
    raw = os.environ.get(key)
    if not raw:
        return None
    try:
        inp, out = (float(x) for x in raw.split(","))
    except ValueError:
        return None
    return inp, out


def price_for(model: str | None) -> tuple[float, float] | None:
    """
    返回 (输入价, 输出价)，每百万 token。认不出来返回 None。
    先精确匹配，再按最长前缀匹配（容忍 claude-haiku-4-5-20251001 这种带日期后缀的 ID）。
    """
    if not model:
        return None
    if (override := _env_override(model)) is not None:
        return override
    if model in PRICES_PER_MTOK:
        return PRICES_PER_MTOK[model]
    matches = [k for k in PRICES_PER_MTOK if model.startswith(k)]
    return PRICES_PER_MTOK[max(matches, key=len)] if matches else None


def cost_usd(model: str | None, input_tokens: int | None,
             output_tokens: int | None) -> float | None:
    """认不出模型、或者没有 token 数时返回 None —— 不猜。"""
    prices = price_for(model)
    if prices is None:
        return None
    inp_price, out_price = prices
    return ((input_tokens or 0) * inp_price + (output_tokens or 0) * out_price) / 1_000_000
