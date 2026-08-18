import pytest

from evaluation.scenarios import run_memory_scenario


@pytest.mark.asyncio
async def test_memory_scenario_passes_and_records_model_requests() -> None:
    """测试多轮记忆场景可以通过并记录请求次数"""

    result = await run_memory_scenario()

    assert result.passed
    assert result.model_requests == 2
    assert result.tool_calls == 0
