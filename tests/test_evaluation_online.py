import pytest

from core.model import TextDelta
from evaluation.fakes import FakeModelClient
from evaluation.online import TimedModelClient


@pytest.mark.asyncio
async def test_timed_model_client_records_request_duration() -> None:
    """测试真实客户端包装器记录请求和耗时"""

    client = TimedModelClient(FakeModelClient([[TextDelta("完成")]]))

    events = [event async for event in client.stream_response([])]

    assert events == [TextDelta("完成")]
    assert len(client.requests) == 1
    assert len(client.durations_ms) == 1
    assert client.durations_ms[0] >= 0
