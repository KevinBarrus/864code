"""测试余额查询实现。"""

import asyncio
import json

import pytest

from core import balance
from core.balance import (
    UNAVAILABLE_BALANCE,
    DeepSeekBalanceProvider,
    UnavailableBalanceProvider,
    create_balance_provider,
)


class FakeResponse:
    """模拟 HTTP 响应，支持上下文管理器协议。"""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        pass

    def read(self) -> bytes:
        return self._data


def _mock_urlopen(monkeypatch: pytest.MonkeyPatch, data: dict | None) -> None:
    """用预置响应替换 urlopen。"""

    if data is None:
        def fail(request, timeout=None):
            raise OSError("模拟网络失败")
        monkeypatch.setattr(balance, "urlopen", fail)
    else:
        payload = json.dumps(data).encode("utf-8")
        monkeypatch.setattr(
            balance,
            "urlopen",
            lambda request, timeout=None: FakeResponse(payload),
        )


def test_unavailable_provider_returns_unavailable_text() -> None:
    """测试默认实现返回不可查询文本。"""

    assert asyncio.run(UnavailableBalanceProvider().get_balance()) == UNAVAILABLE_BALANCE


def test_deepseek_provider_returns_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试成功响应返回余额与币种文本。"""

    _mock_urlopen(
        monkeypatch,
        {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "110.00",
                    "granted_balance": "10.00",
                    "topped_up_balance": "100.00",
                }
            ],
        },
    )
    provider = DeepSeekBalanceProvider("https://api.deepseek.com/", "key")

    assert asyncio.run(provider.get_balance()) == "110.00 CNY"


def test_deepseek_provider_falls_back_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试请求失败时降级为不可查询。"""

    _mock_urlopen(monkeypatch, None)
    provider = DeepSeekBalanceProvider("https://api.deepseek.com/", "key")

    assert asyncio.run(provider.get_balance()) == UNAVAILABLE_BALANCE


def test_deepseek_provider_falls_back_without_balance_infos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试响应缺少余额信息时降级为不可查询。"""

    _mock_urlopen(monkeypatch, {"is_available": True, "balance_infos": []})
    provider = DeepSeekBalanceProvider("https://api.deepseek.com/", "key")

    assert asyncio.run(provider.get_balance()) == UNAVAILABLE_BALANCE


def test_deepseek_provider_falls_back_without_total_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试余额字段缺失时降级为不可查询。"""

    _mock_urlopen(
        monkeypatch,
        {"is_available": True, "balance_infos": [{"currency": "CNY"}]},
    )
    provider = DeepSeekBalanceProvider("https://api.deepseek.com/", "key")

    assert asyncio.run(provider.get_balance()) == UNAVAILABLE_BALANCE


def test_create_provider_uses_deepseek_for_deepseek_endpoint() -> None:
    """测试 DeepSeek 端点使用真实查询实现。"""

    provider = create_balance_provider("https://api.deepseek.com/", "key")

    assert isinstance(provider, DeepSeekBalanceProvider)


def test_create_provider_falls_back_for_other_endpoints() -> None:
    """测试非 DeepSeek 端点使用不可查询降级。"""

    provider = create_balance_provider("https://api.openai.com/v1", "key")

    assert isinstance(provider, UnavailableBalanceProvider)
