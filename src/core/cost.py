"""会话用量累计与成本计算（价格只来自配置，不写死任何厂商价格）。"""

from dataclasses import dataclass

from .config import ModelPrice
from .model import UsageEvent


@dataclass
class UsageTotals:
    """会话累计的 token 用量与成本。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        """累计的总 token 数。"""

        return self.prompt_tokens + self.completion_tokens

    def add(self, usage: UsageEvent, price: ModelPrice | None) -> None:
        """累加一次请求的用量，配置了价格时同步累计成本。"""

        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        if usage.cached_tokens is not None:
            self.cached_tokens += usage.cached_tokens
        if price is not None:
            self.cost += calculate_cost(usage, price)


def calculate_cost(usage: UsageEvent, price: ModelPrice) -> float:
    """按每百万 token 单价计算一次请求的成本（美元）。"""

    cost = usage.prompt_tokens / 1_000_000 * price.input
    cost += usage.completion_tokens / 1_000_000 * price.output
    if usage.cached_tokens is not None and price.cache_read is not None:
        cost += usage.cached_tokens / 1_000_000 * price.cache_read
    return cost


def format_tokens(count: int) -> str:
    """把 token 数压缩为可读单位，规则对齐 Pi 的 formatTokens。"""

    if count < 1000:
        return str(count)
    if count < 10_000:
        return f"{count / 1000:.1f}k"
    if count < 1_000_000:
        return f"{round(count / 1000)}k"
    if count < 10_000_000:
        return f"{count / 1_000_000:.1f}M"
    return f"{round(count / 1_000_000)}M"


def cache_hit_rate(usage: UsageEvent) -> float | None:
    """缓存命中率 = 命中 token / 输入 token，输入为 0 时返回 None。"""

    if usage.prompt_tokens <= 0 or usage.cached_tokens is None:
        return None
    return usage.cached_tokens / usage.prompt_tokens * 100
