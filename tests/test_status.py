from pathlib import Path

import pytest

from core.balance import UnavailableBalanceProvider
from core.status import create_status_info


@pytest.mark.asyncio
async def test_unavailable_balance_provider_returns_default_text() -> None:
    """测试通用余额实现返回暂不可查询。"""

    provider = UnavailableBalanceProvider()

    assert await provider.get_balance() == "暂不可查询"


def test_create_status_info_uses_given_values(tmp_path: Path) -> None:
    """测试状态栏数据能保存模型、余额和工作目录。"""

    status = create_status_info("test-model", "暂不可查询", tmp_path)

    assert status.model_name == "test-model"
    assert status.balance == "暂不可查询"
    assert status.working_directory == tmp_path.resolve()


def test_create_status_info_defaults_to_current_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """测试未传工作目录时使用当前目录。"""

    monkeypatch.chdir(tmp_path)

    status = create_status_info("test-model", "暂不可查询")

    assert status.working_directory == tmp_path.resolve()
