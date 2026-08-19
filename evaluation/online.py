"""提供需要显式确认后才执行的真实模型冒烟评测"""

import argparse
import asyncio
import tempfile
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import perf_counter

from core.agent_loop import AgentLoop, ToolExecutionEvent
from core.config import ConfigError, load_settings
from core.context import estimate_context_tokens
from core.context import ContextBudget, ContextManager
from core.errors import AgentError
from core.model import Message, ModelClient, ModelEvent, ToolCallEvent
from core.openai_client import OpenAICompatibleClient
from core.session import Session
from core.tools import (
    ApprovalDecision,
    ApprovalResult,
    PermissionManager,
    ToolManager,
    create_edit_file_tool,
    create_read_file_tool,
)

from .models import EvaluationAssertion, EvaluationResult
from .events import event_to_record, message_to_record
from .baseline import compare_baseline, create_baseline, load_baseline, write_baseline
from .report import generate_report
from .storage import append_result

ONLINE_SCENARIO_VERSION = "1"


class TimedModelClient:
    """记录真实模型请求耗时的客户端包装器"""

    def __init__(self, client: ModelClient) -> None:
        """保存真实客户端和请求统计"""

        self._client = client
        self.requests: list[list[Message]] = []
        self.durations_ms: list[float] = []

    async def stream_response(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] = (),
    ) -> AsyncIterator[ModelEvent]:
        """记录一次真实流式请求并转发模型事件"""

        self.requests.append(list(messages))
        started_at = perf_counter()
        try:
            async for event in self._client.stream_response(messages, tools):
                yield event
        finally:
            self.durations_ms.append((perf_counter() - started_at) * 1000)

    async def stream_chat(self, messages: Sequence[Message]):
        """记录一次真实摘要请求并转发文本片段"""

        self.requests.append(list(messages))
        started_at = perf_counter()
        try:
            async for chunk in self._client.stream_chat(messages):
                yield chunk
        finally:
            self.durations_ms.append((perf_counter() - started_at) * 1000)


@dataclass
class _OnlineRunState:
    """收集在线场景失败前的最小诊断信息。"""

    scenario: str
    evaluation_type: str
    started_at: float = field(default_factory=perf_counter)
    stage: str = "initialization"
    client: TimedModelClient | None = None
    events: list[dict[str, object]] = field(default_factory=list)

    def failure(self, error: Exception) -> EvaluationResult:
        """将场景异常转换为保留诊断信息的评测结果。"""

        tool_events = [event for event in self.events if event.get("type") == "tool_result"]
        message = f"{type(error).__name__}: {error}"
        return EvaluationResult(
            scenario=self.scenario,
            duration_ms=(perf_counter() - self.started_at) * 1000,
            evaluation_type=self.evaluation_type,  # type: ignore[arg-type]
            model_requests=len(self.client.requests) if self.client else 0,
            tool_calls=len(tool_events),
            tool_failures=sum(bool(event.get("is_error")) for event in tool_events),
            estimated_tokens=(
                sum(estimate_context_tokens(request) for request in self.client.requests)
                if self.client
                else 0
            ),
            model_request_durations_ms=(
                tuple(self.client.durations_ms) if self.client else ()
            ),
            error_category=_error_category(error),
            error_stage=self.stage,
            error_message=message,
            events=tuple(
                [
                    *self.events,
                    {
                        "type": "evaluation_error",
                        "category": _error_category(error),
                        "stage": self.stage,
                        "exception_type": type(error).__name__,
                        "message": str(error),
                    },
                ]
            ),
            assertions=(
                EvaluationAssertion(
                    "online-evaluation-error",
                    False,
                    f"在线评测在 {self.stage} 失败：{message}",
                ),
            ),
        )


async def _run_with_diagnostics(
    state: _OnlineRunState,
    runner: Awaitable[EvaluationResult],
) -> EvaluationResult:
    """执行在线场景并将未处理异常转换为评测结果。"""

    try:
        return await runner
    except Exception as error:
        return state.failure(error)


def _error_category(error: Exception) -> str:
    """按异常来源标记评测失败类别。"""

    if isinstance(error, AgentError):
        return error.category
    if isinstance(error, ConfigError):
        return "configuration"
    if isinstance(error, OSError):
        return "environment"
    return "runner"


async def run_online_smoke(env_path: Path | None = None) -> EvaluationResult:
    """在临时工作区执行一条真实模型主链路冒烟评测"""

    state = _OnlineRunState("online_main_smoke", "real-task")
    return await _run_with_diagnostics(state, _run_online_smoke(state, env_path))


async def _run_online_smoke(
    state: _OnlineRunState,
    env_path: Path | None,
) -> EvaluationResult:
    """执行真实模型主链路并持续更新诊断状态。"""

    state.stage = "load-settings"
    settings = load_settings(env_path)
    with tempfile.TemporaryDirectory(prefix="864code-online-") as directory:
        workspace = Path(directory)
        target = workspace / "note.txt"
        target.write_text("before\n", encoding="utf-8")
        client = TimedModelClient(OpenAICompatibleClient(settings))
        state.client = client

        async def approve_write(definition, tool_call):
            return ApprovalResult(ApprovalDecision.ALLOW_ONCE)

        manager = ToolManager(
            permission_manager=PermissionManager(approve_write),
        )
        manager.register_local(*create_read_file_tool(workspace))
        manager.register_local(*create_edit_file_tool(workspace))
        session = Session(workspace)
        events = state.events
        events.append(
            message_to_record(
                Message(
                    role="user",
                    content="请先读取 note.txt，然后把内容从 before 改成 after，完成后告诉我结果",
                )
            )
        )
        session.add_user_message(
            "请先读取 note.txt，然后把内容从 before 改成 after，完成后告诉我结果"
        )

        async def collect_event(event: object) -> None:
            events.append(event_to_record(event))

        started_at = perf_counter()
        state.stage = "agent-loop"
        result = await AgentLoop(client, manager).run(
            session.get_messages(),
            on_event=collect_event,
        )
        for message in result.new_messages:
            session.add_message(message)
        state.stage = "session-persistence"
        persistence_ok = session.flush_persistence() and session.close()
        restored = Session.restore(workspace, session.session_id)
        restored_messages = restored.get_messages()
        restored.close()

        tool_events = [event for event in events if event["type"] == "tool_result"]
        tool_names = [event["name"] for event in tool_events]
        events.append(message_to_record(Message(role="assistant", content=result.final_content)))
        assertions = (
            EvaluationAssertion(
                "file-content",
                target.read_text(encoding="utf-8").strip() == "after",
                "真实模型没有完成文件修改",
            ),
            EvaluationAssertion(
                "tool-chain",
                "read_file" in tool_names and "edit_file" in tool_names,
                "真实模型没有完成读取和编辑工具调用",
            ),
            EvaluationAssertion(
                "session-restore",
                restored_messages == session.get_messages(),
                "真实 Session 恢复后的消息不一致",
            ),
            EvaluationAssertion(
                "persistence",
                persistence_ok,
                "真实 Session Flush 失败",
            ),
        )
        return EvaluationResult(
            scenario="online_main_smoke",
            duration_ms=(perf_counter() - started_at) * 1000,
            evaluation_type="real-task",
            model_requests=len(client.requests),
            tool_calls=len(tool_events),
            tool_failures=sum(bool(event["is_error"]) for event in tool_events),
            estimated_tokens=sum(
                estimate_context_tokens(request) for request in client.requests
            ),
            persistence_degraded=not persistence_ok,
            model_request_durations_ms=tuple(client.durations_ms),
            events=tuple(events),
            assertions=assertions,
        )


async def run_online_suite(
    env_path: Path | None = None,
    repetitions: int = 6,
    scenario: str = "main",
) -> list[EvaluationResult]:
    """重复执行在线主链路并保留单次失败结果"""

    if repetitions <= 0:
        raise ValueError("在线评测重复次数必须大于 0")
    results: list[EvaluationResult] = []
    runners = {
        "main": run_online_smoke,
        "context-compaction": run_online_compaction_smoke,
        "network-error": run_online_network_error_smoke,
    }
    if scenario not in runners:
        raise ValueError(f"不支持的在线评测场景：{scenario}")
    for repetition in range(1, repetitions + 1):
        try:
            result = await runners[scenario](env_path)
        except Exception as error:
            result = EvaluationResult(
                scenario=f"online_{scenario}",
                duration_ms=0,
                evaluation_type="online-special",
                error_category=_error_category(error),
                error_stage="suite",
                error_message=f"{type(error).__name__}: {error}",
                events=(
                    {
                        "type": "evaluation_error",
                        "category": _error_category(error),
                        "stage": "suite",
                        "exception_type": type(error).__name__,
                        "message": str(error),
                    },
                ),
                assertions=(
                    EvaluationAssertion(
                        "online-evaluation-error",
                        False,
                        f"在线评测在 suite 失败：{type(error).__name__}: {error}",
                    ),
                ),
            )
        results.append(replace(result, repetition=repetition))
    return results


async def run_online_compaction_smoke(
    env_path: Path | None = None,
) -> EvaluationResult:
    """使用真实模型执行一次上下文压缩和 Session 恢复冒烟评测"""

    state = _OnlineRunState("online_context_compaction", "online-special")
    return await _run_with_diagnostics(
        state,
        _run_online_compaction_smoke(state, env_path),
    )


async def _run_online_compaction_smoke(
    state: _OnlineRunState,
    env_path: Path | None,
) -> EvaluationResult:
    """执行上下文压缩专项并持续更新诊断状态。"""

    state.stage = "load-settings"
    settings = load_settings(env_path)
    with tempfile.TemporaryDirectory(prefix="864code-compaction-") as directory:
        workspace = Path(directory)
        client = TimedModelClient(OpenAICompatibleClient(settings))
        state.client = client
        session = Session(workspace)
        for index in range(4):
            session.add_user_message(f"历史任务 {index}: " + "x" * 180)
            session.add_assistant_message(f"历史回复 {index}: " + "x" * 180)
        manager = ContextManager(ContextBudget(500, 100, 120))
        started_at = perf_counter()
        state.stage = "context-compaction"
        result = await manager.build_for_model_result(
            client,
            session.get_messages(),
            session.get_compactions(),
        )
        if result.compaction is not None:
            session.add_compaction(result.compaction)
        state.stage = "session-persistence"
        persistence_ok = session.flush_persistence() and session.close()
        restored = Session.restore(workspace, session.session_id)
        restored_compactions = restored.get_compactions()
        restored.close()
        assertions = (
            EvaluationAssertion(
                "compaction-created",
                result.compaction is not None and not result.fallback_used,
                "真实模型没有生成有效上下文摘要",
            ),
            EvaluationAssertion(
                "session-restore",
                bool(restored_compactions) == (result.compaction is not None),
                "压缩记录无法从 Session 恢复",
            ),
            EvaluationAssertion(
                "persistence",
                persistence_ok,
                "上下文压缩 Session 持久化失败",
            ),
        )
        return EvaluationResult(
            scenario="online_context_compaction",
            duration_ms=(perf_counter() - started_at) * 1000,
            evaluation_type="online-special",
            model_requests=len(client.requests),
            compactions=int(result.compaction is not None),
            estimated_tokens=sum(
                estimate_context_tokens(request) for request in client.requests
            ),
            persistence_degraded=not persistence_ok,
            model_request_durations_ms=tuple(client.durations_ms),
            assertions=assertions,
        )


async def run_online_network_error_smoke(
    env_path: Path | None = None,
) -> EvaluationResult:
    """通过本机不可用端口验证真实网络异常处理"""

    state = _OnlineRunState("online_network_error", "online-special")
    return await _run_with_diagnostics(
        state,
        _run_online_network_error_smoke(state, env_path),
    )


async def _run_online_network_error_smoke(
    state: _OnlineRunState,
    env_path: Path | None,
) -> EvaluationResult:
    """执行网络异常专项并持续更新诊断状态。"""

    state.stage = "load-settings"
    settings = load_settings(env_path)
    unavailable_settings = replace(settings, base_url="http://127.0.0.1:1")
    client = TimedModelClient(OpenAICompatibleClient(unavailable_settings))
    state.client = client
    started_at = perf_counter()
    error: AgentError | None = None
    try:
        state.stage = "network-request"
        await AgentLoop(client, ToolManager()).run(
            [Message(role="user", content="测试网络异常处理")]
        )
    except AgentError as exc:
        error = exc
    assertions = (
        EvaluationAssertion(
            "network-category",
            error is not None and error.category == "network",
            "真实连接失败没有转换为 network 错误",
        ),
        EvaluationAssertion(
            "retry-once",
            len(client.requests) == 2,
            "网络错误没有按策略重试一次",
        ),
        EvaluationAssertion(
            "safe-error",
            error is not None and error.cause is not None,
            "网络错误没有保留内部诊断原因",
        ),
    )
    return EvaluationResult(
        scenario="online_network_error",
        duration_ms=(perf_counter() - started_at) * 1000,
        evaluation_type="online-special",
        model_requests=len(client.requests),
        retries=max(0, len(client.requests) - 1),
        estimated_tokens=sum(
            estimate_context_tokens(request) for request in client.requests
        ),
        model_request_durations_ms=tuple(client.durations_ms),
        events=(
            message_to_record(Message(role="user", content="测试网络异常处理")),
            {"type": "model_error", "category": error.category if error else None},
        ),
        assertions=assertions,
    )


def main() -> int:
    """处理真实在线评测命令行参数"""

    parser = argparse.ArgumentParser(description="运行 864code 在线冒烟评测")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认发起真实模型请求并可能产生费用",
    )
    parser.add_argument("--env", type=Path, help="指定 .env 配置文件")
    parser.add_argument(
        "--repetitions",
        type=int,
        default=6,
        help="在线主链路重复次数，默认 6 次",
    )
    parser.add_argument(
        "--scenario",
        choices=("main", "context-compaction", "network-error"),
        default="main",
        help="在线专项场景",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation-results/online.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evaluation-results/online-report.html"),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("evaluation-results/online-baseline.json"),
    )
    args = parser.parse_args()
    if not args.confirm:
        print("在线评测会发起真实模型请求，请添加 --confirm 后运行")
        return 2

    settings = load_settings(args.env)
    metadata = {
        "model_name": settings.model_name,
        "base_url": settings.base_url,
        "context_window": str(settings.context_window),
        "reserve_tokens": str(settings.reserve_tokens),
        "keep_recent_tokens": str(settings.keep_recent_tokens),
        "scenario": args.scenario,
        "scenario_version": ONLINE_SCENARIO_VERSION,
    }
    results = asyncio.run(
        run_online_suite(
            args.env,
            args.repetitions,
            scenario=args.scenario,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("", encoding="utf-8")
    for result in results:
        append_result(args.output, result)
    regression = None
    if args.baseline.exists():
        regression = compare_baseline(
            results,
            load_baseline(args.baseline),
            metadata,
        )
    elif all(result.passed for result in results):
        write_baseline(args.baseline, create_baseline(results, metadata))
    generate_report(args.report, results, regression)
    passed = sum(result.passed for result in results)
    print(f"online evaluation: {passed}/{len(results)} repetitions passed")
    if regression is not None:
        print(f"baseline regression: {'passed' if regression.passed else 'failed'}")
    print(f"results: {args.output}")
    print(f"report: {args.report}")
    return 0 if passed == len(results) and (regression is None or regression.passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
