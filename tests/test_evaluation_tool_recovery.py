from pathlib import Path

import pytest

from evaluation.scenarios import run_tool_recovery_scenario


@pytest.mark.asyncio
async def test_tool_recovery_scenario_continues_after_tool_failure(
    tmp_path: Path,
) -> None:
    """测试工具失败后 AgentLoop 可以继续执行并完成任务"""

    result = await run_tool_recovery_scenario(tmp_path)

    assert result.passed
    assert result.model_requests == 3
    assert result.tool_calls == 2
    assert result.tool_failures == 1
