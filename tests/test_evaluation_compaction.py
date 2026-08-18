from pathlib import Path

import pytest

from evaluation.scenarios import run_compaction_restore_scenario


@pytest.mark.asyncio
async def test_compaction_restore_scenario_preserves_context(
    tmp_path: Path,
) -> None:
    """测试上下文压缩后恢复 Session 可以重建相同上下文"""

    result = await run_compaction_restore_scenario(tmp_path)

    assert result.passed
    assert result.model_requests == 1
    assert result.compactions == 1
