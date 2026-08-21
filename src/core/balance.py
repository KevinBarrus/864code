"""定义模型余额查询接口。"""

import asyncio
import json
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import urljoin
from urllib.request import Request, urlopen

UNAVAILABLE_BALANCE = "unavailable"


class BalanceProvider(Protocol):
    """不同模型服务商的余额查询实现需要遵循的接口。"""

    async def get_balance(self) -> str:
        """返回用于状态栏显示的余额文本。"""


class UnavailableBalanceProvider:
    """通用 OpenAI-compatible API 的默认余额查询实现。"""

    async def get_balance(self) -> str:
        """通用接口没有统一余额 API，因此返回不可查询状态。"""

        return UNAVAILABLE_BALANCE


class DeepSeekBalanceProvider:
    """查询 DeepSeek /user/balance 接口的余额实现。"""

    def __init__(self, base_url: str, api_key: str) -> None:
        """保存服务地址与 API key。"""

        self._base_url = base_url
        self._api_key = api_key

    async def get_balance(self) -> str:
        """调用 /user/balance 返回余额文本，任何失败都降级为不可查询。"""

        try:
            return await asyncio.to_thread(self._fetch_balance)
        except Exception:
            return UNAVAILABLE_BALANCE

    def _fetch_balance(self) -> str:
        """同步请求余额接口并解析余额文本。"""

        url = urljoin(self._base_url, "/user/balance")
        request = Request(
            url,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return _format_balance(data)


def create_balance_provider(base_url: str, api_key: str) -> BalanceProvider:
    """按服务地址选择余额查询实现，非 DeepSeek 端点使用不可查询降级。"""

    if "deepseek" in base_url.lower():
        return DeepSeekBalanceProvider(base_url, api_key)
    return UnavailableBalanceProvider()


def _format_balance(data: Mapping) -> str:
    """从余额响应中提取第一项余额文本，无法解析时返回不可查询。"""

    infos = data.get("balance_infos") or []
    if not infos:
        return UNAVAILABLE_BALANCE
    info = infos[0]
    total_balance = info.get("total_balance")
    if total_balance is None:
        return UNAVAILABLE_BALANCE
    currency = str(info.get("currency", "")).strip()
    return f"{total_balance} {currency}".strip()
