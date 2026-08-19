import pytest

from core.config import ConfigError, Settings
from core.model import Message, TextDelta, ToolCall, ToolCallEvent
from evaluation.fakes import FakeModelClient
from evaluation.models import EvaluationAssertion, EvaluationResult
from evaluation.online import (
    ONLINE_FILE_TASKS,
    TimedModelClient,
    run_online_file_task,
    run_online_suite,
)


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
    """测试在线主任务会运行全部文件任务并保留失败。"""

    calls: list[str] = []

    async def fake_run(task, env_path=None):
        calls.append(task.name)
        if task.name == "online_multi_file_edit":
            raise RuntimeError("模拟在线失败")
        return EvaluationResult(
            scenario=task.name,
            duration_ms=10,
            evaluation_type="real-task",
            assertions=(EvaluationAssertion("ok", True),),
        )

    monkeypatch.setattr("evaluation.online.run_online_file_task", fake_run)

    results = await run_online_suite(repetitions=1)

    assert calls == [task.name for task in ONLINE_FILE_TASKS]
    assert [result.repetition for result in results] == [1, 1, 1]
    assert [result.passed for result in results] == [True, False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task", "responses"),
    [
        (
            ONLINE_FILE_TASKS[0],
            [
                [ToolCallEvent(ToolCall("read", "read_file", {"path": "note.txt"}))],
                [
                    ToolCallEvent(
                        ToolCall(
                            "edit",
                            "edit_file",
                            {
                                "path": "note.txt",
                                "old_content": "before\n",
                                "new_content": "after\n",
                            },
                        )
                    )
                ],
                [TextDelta("note.txt 已完成修改")],
            ],
        ),
        (
            ONLINE_FILE_TASKS[1],
            [
                [
                    ToolCallEvent(ToolCall("read-config", "read_file", {"path": "config.txt"})),
                    ToolCallEvent(ToolCall("read-note", "read_file", {"path": "note.txt"})),
                ],
                [
                    ToolCallEvent(
                        ToolCall(
                            "edit-config",
                            "edit_file",
                            {
                                "path": "config.txt",
                                "old_content": "old-config\n",
                                "new_content": "new-config\n",
                            },
                        )
                    ),
                    ToolCallEvent(
                        ToolCall(
                            "edit-note",
                            "edit_file",
                            {
                                "path": "note.txt",
                                "old_content": "old-note\n",
                                "new_content": "new-note\n",
                            },
                        )
                    ),
                ],
                [TextDelta("config.txt 和 note.txt 已完成修改")],
            ],
        ),
        (
            ONLINE_FILE_TASKS[2],
            [
                [ToolCallEvent(ToolCall("missing", "read_file", {"path": "missing.txt"}))],
                [ToolCallEvent(ToolCall("read", "read_file", {"path": "note.txt"}))],
                [
                    ToolCallEvent(
                        ToolCall(
                            "edit",
                            "edit_file",
                            {
                                "path": "note.txt",
                                "old_content": "before\n",
                                "new_content": "after\n",
                            },
                        )
                    )
                ],
                [TextDelta("note.txt 已完成修改")],
            ],
        ),
    ],
)
async def test_online_file_tasks_validate_expected_agent_behavior(
    task,
    responses,
    monkeypatch,
) -> None:
    """测试三类真实任务均验证文件、工具顺序和最终回复。"""

    client = FakeModelClient(responses)
    monkeypatch.setattr(
        "evaluation.online.load_settings",
        lambda env_path=None: Settings("https://example.com", "test", "key"),
    )
    monkeypatch.setattr("evaluation.online.OpenAICompatibleClient", lambda settings: client)

    result = await run_online_file_task(task)

    assert result.passed


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
