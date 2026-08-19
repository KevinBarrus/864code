import pytest

from core.config import ConfigError
from core.model import Message, TextDelta
from evaluation.fakes import FakeModelClient
from evaluation.models import EvaluationAssertion, EvaluationResult
from evaluation.online import TimedModelClient, run_online_suite


@pytest.mark.asyncio
async def test_timed_model_client_records_request_duration() -> None:
    """测试真实客户端包装器记录请求和耗时"""

    client = TimedModelClient(FakeModelClient([[TextDelta("完成")]]))

    events = [event async for event in client.stream_response([])]

    assert events == [TextDelta("完成")]
    assert len(client.requests) == 1
    assert len(client.durations_ms) == 1
    assert client.durations_ms[0] >= 0


@pytest.mark.asyncio
async def test_timed_model_client_records_summary_request_duration() -> None:
    """测试客户端包装器记录摘要请求耗时"""

    client = TimedModelClient(FakeModelClient([[TextDelta("摘要")]]))

    chunks = [chunk async for chunk in client.stream_chat([Message("user", "历史")])]

    assert chunks == ["摘要"]
    assert len(client.requests) == 1
    assert len(client.durations_ms) == 1


@pytest.mark.asyncio
async def test_online_suite_runs_requested_repetitions_and_keeps_failures(
    monkeypatch,
) -> None:
    """测试在线评测套件会完成全部重复运行"""

    calls = 0

    async def fake_run(env_path=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("模拟在线失败")
        return EvaluationResult(
            scenario="online_main_smoke",
            duration_ms=10,
            assertions=(EvaluationAssertion("ok", True),),
        )

    monkeypatch.setattr("evaluation.online.run_online_smoke", fake_run)

    results = await run_online_suite(repetitions=3)

    assert [result.repetition for result in results] == [1, 2, 3]
    assert [result.passed for result in results] == [True, False, True]


@pytest.mark.asyncio
async def test_online_suite_dispatches_network_error_scenario(monkeypatch) -> None:
    """测试在线评测套件能调度网络异常专项场景"""

    async def fake_run(env_path=None):
        return EvaluationResult(
            scenario="online_network_error",
            duration_ms=10,
            assertions=(EvaluationAssertion("ok", True),),
        )

    monkeypatch.setattr("evaluation.online.run_online_network_error_smoke", fake_run)

    results = await run_online_suite(repetitions=1, scenario="network-error")

    assert results[0].scenario == "online_network_error"
    assert results[0].passed


@pytest.mark.asyncio
async def test_online_smoke_keeps_configuration_failure_diagnostics(monkeypatch) -> None:
    """测试在线场景会保留配置失败的类别和阶段。"""

    def fail_load_settings(env_path=None):
        raise ConfigError("缺少模型配置")

    monkeypatch.setattr("evaluation.online.load_settings", fail_load_settings)

    from evaluation.online import run_online_smoke

    result = await run_online_smoke()

    assert result.passed is False
    assert result.error_category == "configuration"
    assert result.error_stage == "load-settings"
    assert "ConfigError" in (result.error_message or "")
    assert result.events[-1]["type"] == "evaluation_error"
