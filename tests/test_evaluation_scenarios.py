import pytest

from evaluation.scenarios import (
    run_cancelled_tool_restore_scenario,
    run_memory_scenario,
)


@pytest.mark.asyncio
async def test_memory_scenario_passes_and_records_model_requests(tmp_path) -> None:
    """测试 Session 重启后的多轮历史场景可以通过。"""

    result = await run_memory_scenario(tmp_path)

    assert result.passed
    assert result.model_requests == 2
    assert result.tool_calls == 0


@pytest.mark.asyncio
async def test_cancelled_tool_restore_scenario_passes(tmp_path) -> None:
    """测试取消工具链恢复场景可以通过。"""

    result = await run_cancelled_tool_restore_scenario(tmp_path)

    assert result.passed
