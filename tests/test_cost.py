"""用量累计与成本计算的单元测试。"""

import pytest

from core.config import ModelPrice
from core.cost import UsageTotals, cache_hit_rate, calculate_cost, format_tokens
from core.model import UsageEvent


def test_calculate_cost_multiplies_by_price_per_million() -> None:
    """测试成本 = 用量 / 100 万 × 单价。"""

    price = ModelPrice(input=0.55, output=2.19, cache_read=0.14)
    usage = UsageEvent(prompt_tokens=1_000_000, completion_tokens=100_000, total_tokens=1_100_000)

    cost = calculate_cost(usage, price)

    assert cost == pytest.approx(0.55 + 0.219)


def test_calculate_cost_includes_cache_read() -> None:
    """测试缓存命中 token 按 cache_read 单价计费。"""

    price = ModelPrice(input=0.55, output=2.19, cache_read=0.14)
    usage = UsageEvent(
        prompt_tokens=1_000_000,
        completion_tokens=0,
        total_tokens=1_000_000,
        cached_tokens=500_000,
    )

    cost = calculate_cost(usage, price)

    assert cost == pytest.approx(0.55 + 0.07)


def test_calculate_cost_skips_cache_when_no_cache_price() -> None:
    """测试未配置 cache_read 时缓存 token 不计费。"""

    price = ModelPrice(input=0.55, output=2.19)
    usage = UsageEvent(
        prompt_tokens=1_000_000,
        completion_tokens=0,
        total_tokens=1_000_000,
        cached_tokens=500_000,
    )

    assert calculate_cost(usage, price) == pytest.approx(0.55)


def test_usage_totals_accumulates_without_price() -> None:
    """测试无价格配置时只累计用量不计算成本。"""

    totals = UsageTotals()
    totals.add(
        UsageEvent(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        None,
    )
    totals.add(
        UsageEvent(prompt_tokens=200, completion_tokens=30, total_tokens=230),
        None,
    )

    assert totals.prompt_tokens == 300
    assert totals.completion_tokens == 80
    assert totals.total_tokens == 380
    assert totals.cost == 0.0


def test_usage_totals_accumulates_cost_with_price() -> None:
    """测试配置价格时每轮成本累计。"""

    totals = UsageTotals()
    price = ModelPrice(input=1.0, output=2.0)
    totals.add(
        UsageEvent(prompt_tokens=1_000_000, completion_tokens=0, total_tokens=1_000_000),
        price,
    )
    totals.add(
        UsageEvent(prompt_tokens=0, completion_tokens=500_000, total_tokens=500_000),
        price,
    )

    assert totals.cost == pytest.approx(1.0 + 1.0)


def test_format_tokens_units() -> None:
    """测试 token 单位压缩规则（对齐 Pi formatTokens）。"""

    assert format_tokens(345) == "345"
    assert format_tokens(1200) == "1.2k"
    assert format_tokens(10000) == "10k"
    assert format_tokens(204_000_000) == "204M"
    assert format_tokens(5_500_000) == "5.5M"


def test_cache_hit_rate() -> None:
    """测试缓存命中率计算与缺失容错。"""

    usage = UsageEvent(
        prompt_tokens=1000,
        completion_tokens=0,
        total_tokens=1000,
        cached_tokens=900,
    )

    assert cache_hit_rate(usage) == pytest.approx(90.0)
    assert cache_hit_rate(UsageEvent(0, 0, 0)) is None
    assert cache_hit_rate(
        UsageEvent(100, 0, 100, cached_tokens=None)
    ) is None
