import pytest

from evaluation.scenarios import run_model_retry_scenario


@pytest.mark.asyncio
async def test_model_retry_scenario_retries_once_and_completes() -> None:
    """测试模型网络错误重试一次后可以完成任务"""

    result = await run_model_retry_scenario()

    assert result.passed
    assert result.model_requests == 2
    assert result.retries == 1
