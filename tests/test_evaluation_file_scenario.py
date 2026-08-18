from pathlib import Path

import pytest

from evaluation.scenarios import run_file_edit_scenario


@pytest.mark.asyncio
async def test_file_edit_scenario_validates_tool_chain_and_file_content(
    tmp_path: Path,
) -> None:
    """测试文件场景验证工具链和最终文件内容"""

    result = await run_file_edit_scenario(tmp_path)

    assert result.passed
    assert result.model_requests == 3
    assert result.tool_calls == 2
    assert result.tool_failures == 0
