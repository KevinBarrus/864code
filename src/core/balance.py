"""定义模型余额查询接口。"""

from typing import Protocol


class BalanceProvider(Protocol):
    """不同模型服务商的余额查询实现需要遵循的接口。"""

    async def get_balance(self) -> str:
        """返回用于状态栏显示的余额文本。"""


class UnavailableBalanceProvider:
    """通用 OpenAI-compatible API 的默认余额查询实现。"""

    async def get_balance(self) -> str:
        """通用接口没有统一余额 API，因此返回不可查询状态。"""

        return "暂不可查询"
