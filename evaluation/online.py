"""提供需要显式确认后才执行的真实模型冒烟评测"""

import argparse
import asyncio
import tempfile
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from core.agent_loop import AgentLoop, ToolExecutionEvent
from core.config import load_settings
from core.context import estimate_context_tokens
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
from .report import generate_report
from .storage import append_result


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


async def run_online_smoke(env_path: Path | None = None) -> EvaluationResult:
    """在临时工作区执行一条真实模型主链路冒烟评测"""

    settings = load_settings(env_path)
    with tempfile.TemporaryDirectory(prefix="864code-online-") as directory:
        workspace = Path(directory)
        target = workspace / "note.txt"
        target.write_text("before\n", encoding="utf-8")
        client = TimedModelClient(OpenAICompatibleClient(settings))

        async def approve_write(definition, tool_call):
            return ApprovalResult(ApprovalDecision.ALLOW_ONCE)

        manager = ToolManager(
            permission_manager=PermissionManager(approve_write),
        )
        manager.register_local(*create_read_file_tool(workspace))
        manager.register_local(*create_edit_file_tool(workspace))
        session = Session(workspace)
        events: list[dict[str, object]] = [
            message_to_record(
                Message(
                    role="user",
                    content="请先读取 note.txt，然后把内容从 before 改成 after，完成后告诉我结果",
                )
            )
        ]
        session.add_user_message(
            "请先读取 note.txt，然后把内容从 before 改成 after，完成后告诉我结果"
        )

        async def collect_event(event: object) -> None:
            events.append(event_to_record(event))

        started_at = perf_counter()
        result = await AgentLoop(client, manager).run(
            session.get_messages(),
            on_event=collect_event,
        )
        for message in result.messages[len(session.get_messages()) :]:
            session.add_message(message)
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
) -> list[EvaluationResult]:
    """重复执行在线主链路并保留单次失败结果"""

    if repetitions <= 0:
        raise ValueError("在线评测重复次数必须大于 0")
    results: list[EvaluationResult] = []
    for repetition in range(1, repetitions + 1):
        try:
            result = await run_online_smoke(env_path)
        except Exception:
            result = EvaluationResult(
                scenario="online_main_smoke",
                duration_ms=0,
                assertions=(
                    EvaluationAssertion(
                        "runner-error",
                        False,
                        "在线评测运行失败",
                    ),
                ),
            )
        results.append(replace(result, repetition=repetition))
    return results


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
        "--output",
        type=Path,
        default=Path("evaluation-results/online.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evaluation-results/online-report.html"),
    )
    args = parser.parse_args()
    if not args.confirm:
        print("在线评测会发起真实模型请求，请添加 --confirm 后运行")
        return 2

    results = asyncio.run(run_online_suite(args.env, args.repetitions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("", encoding="utf-8")
    for result in results:
        append_result(args.output, result)
    generate_report(args.report, results)
    passed = sum(result.passed for result in results)
    print(f"online evaluation: {passed}/{len(results)} repetitions passed")
    print(f"results: {args.output}")
    print(f"report: {args.report}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
