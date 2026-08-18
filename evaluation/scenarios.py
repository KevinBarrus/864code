"""定义可重复执行的离线评测场景"""

from time import perf_counter

from core.agent_loop import AgentLoop, ToolExecutionEvent
from core.context import estimate_context_tokens
from core.context import ContextBudget, ContextManager
from core.memory import Memory
from core.model import Message, TextDelta, ToolCall, ToolCallEvent
from core.tools import (
    ApprovalDecision,
    ApprovalResult,
    PermissionManager,
    ToolManager,
    create_edit_file_tool,
    create_read_file_tool,
)
from core.session import Session

from .fakes import FakeModelClient
from .models import EvaluationAssertion, EvaluationResult, EvaluationScenario


MEMORY_SCENARIO = EvaluationScenario(
    name="multi_turn_memory",
    description="验证多轮请求会携带之前的对话历史",
)

FILE_EDIT_SCENARIO = EvaluationScenario(
    name="file_edit",
    description="验证模型可以读取文件、修改文件并完成任务",
)

TOOL_RECOVERY_SCENARIO = EvaluationScenario(
    name="tool_failure_recovery",
    description="验证工具失败后模型可以修正调用并继续完成任务",
)

COMPACTION_RESTORE_SCENARIO = EvaluationScenario(
    name="compaction_restore",
    description="验证上下文压缩记录和 Session 恢复结果一致",
)


async def run_memory_scenario() -> EvaluationResult:
    """运行多轮记忆场景并返回结构化结果"""

    client = FakeModelClient(
        [
            [TextDelta("我记住了项目目标")],
            [TextDelta("根据之前的目标继续执行")],
        ]
    )
    memory = Memory()
    loop = AgentLoop(client, ToolManager())
    started_at = perf_counter()

    memory.add_user_message("项目目标是实现一个简洁的 Coding Agent")
    first_result = await loop.run(memory.get_messages())
    memory.add_message(first_result.messages[-1])

    memory.add_user_message("继续执行")
    second_result = await loop.run(memory.get_messages())

    has_history = (
        len(client.requests) == 2
        and client.requests[1][0]
        == Message(role="user", content="项目目标是实现一个简洁的 Coding Agent")
        and client.requests[1][1]
        == Message(role="assistant", content="我记住了项目目标")
    )
    assertions = (
        EvaluationAssertion("history-forwarded", has_history, "第二轮未携带第一轮历史"),
        EvaluationAssertion(
            "final-response",
            second_result.final_content == "根据之前的目标继续执行",
            "第二轮模型回复不符合预期",
        ),
    )
    return EvaluationResult(
        scenario=MEMORY_SCENARIO.name,
        duration_ms=(perf_counter() - started_at) * 1000,
        model_requests=len(client.requests),
        estimated_tokens=sum(
            len(message.content) // 4 for request in client.requests for message in request
        ),
        assertions=assertions,
    )


async def run_file_edit_scenario(workspace) -> EvaluationResult:
    """运行文件读取与修改场景并返回结构化结果"""

    target = workspace / "note.txt"
    target.write_text("old\n", encoding="utf-8")
    read_call = ToolCall("read-1", "read_file", {"path": "note.txt"})
    edit_call = ToolCall(
        "edit-1",
        "edit_file",
        {"path": "note.txt", "old_content": "old\n", "new_content": "new\n"},
    )
    client = FakeModelClient(
        [
            [ToolCallEvent(read_call)],
            [ToolCallEvent(edit_call)],
            [TextDelta("文件已完成修改")],
        ]
    )

    async def approve_write(definition, tool_call):
        return ApprovalResult(ApprovalDecision.ALLOW_ONCE)

    manager = ToolManager(permission_manager=PermissionManager(approve_write))
    manager.register_local(*create_read_file_tool(workspace))
    manager.register_local(*create_edit_file_tool(workspace))
    events: list[object] = []

    async def collect_event(event: object) -> None:
        events.append(event)

    started_at = perf_counter()
    result = await AgentLoop(client, manager).run(
        [Message(role="user", content="把 note.txt 的内容改成 new")],
        on_event=collect_event,
    )
    tool_events = [event for event in events if isinstance(event, ToolExecutionEvent)]
    assertions = (
        EvaluationAssertion(
            "file-content",
            target.read_text(encoding="utf-8") == "new\n",
            "文件内容未修改为预期值",
        ),
        EvaluationAssertion(
            "tool-chain",
            [event.tool_call.name for event in tool_events]
            == ["read_file", "edit_file"],
            "工具调用链不符合预期",
        ),
        EvaluationAssertion(
            "final-response",
            result.final_content == "文件已完成修改",
            "模型未返回最终完成消息",
        ),
    )
    return EvaluationResult(
        scenario=FILE_EDIT_SCENARIO.name,
        duration_ms=(perf_counter() - started_at) * 1000,
        model_requests=len(client.requests),
        tool_calls=len(tool_events),
        tool_failures=sum(event.result.is_error for event in tool_events),
        estimated_tokens=sum(
            estimate_context_tokens(request) for request in client.requests
        ),
        assertions=assertions,
    )


async def run_tool_recovery_scenario(workspace) -> EvaluationResult:
    """运行工具失败恢复场景并返回结构化结果"""

    (workspace / "available.txt").write_text("可读取内容", encoding="utf-8")
    failed_call = ToolCall("read-1", "read_file", {"path": "missing.txt"})
    recovered_call = ToolCall("read-2", "read_file", {"path": "available.txt"})
    client = FakeModelClient(
        [
            [ToolCallEvent(failed_call)],
            [ToolCallEvent(recovered_call)],
            [TextDelta("已根据工具错误修正路径并完成读取")],
        ]
    )
    manager = ToolManager()
    manager.register_local(*create_read_file_tool(workspace))
    events: list[object] = []

    async def collect_event(event: object) -> None:
        events.append(event)

    started_at = perf_counter()
    result = await AgentLoop(client, manager).run(
        [Message(role="user", content="读取 available.txt")],
        on_event=collect_event,
    )
    tool_events = [event for event in events if isinstance(event, ToolExecutionEvent)]
    failed_events = [event for event in tool_events if event.result.is_error]
    assertions = (
        EvaluationAssertion(
            "tool-error-returned",
            len(failed_events) == 1
            and failed_events[0].result.error_category == "tool_execution",
            "工具错误没有作为结构化结果返回",
        ),
        EvaluationAssertion(
            "tool-retry-call",
            [event.tool_call.arguments["path"] for event in tool_events]
            == ["missing.txt", "available.txt"],
            "模型没有修正工具调用参数",
        ),
        EvaluationAssertion(
            "recovery-completed",
            result.final_content == "已根据工具错误修正路径并完成读取",
            "工具失败后 AgentLoop 未完成恢复",
        ),
    )
    return EvaluationResult(
        scenario=TOOL_RECOVERY_SCENARIO.name,
        duration_ms=(perf_counter() - started_at) * 1000,
        model_requests=len(client.requests),
        tool_calls=len(tool_events),
        tool_failures=len(failed_events),
        estimated_tokens=sum(
            estimate_context_tokens(request) for request in client.requests
        ),
        assertions=assertions,
    )


async def run_compaction_restore_scenario(workspace) -> EvaluationResult:
    """运行上下文压缩与 Session 恢复场景并返回结构化结果"""

    summary = """## Goal
实现 Coding Agent
## Progress
已完成核心功能
## Key Decisions
保持架构简洁
## Next Steps
继续评测
## Critical Context
保留任务目标和关键决策"""
    session = Session(workspace)
    session.add_user_message("旧问题" + "x" * 160)
    session.add_assistant_message("旧回答" + "x" * 160)
    session.add_user_message("新问题")
    session.add_assistant_message("新回答")
    client = FakeModelClient([[TextDelta(summary)]])
    manager = ContextManager(ContextBudget(100, 20, 20))
    started_at = perf_counter()

    first_result = await manager.build_for_model_result(
        client,
        session.get_messages(),
    )
    if first_result.compaction is not None:
        session.add_compaction(first_result.compaction)
    session.close()

    restored = Session.restore(workspace, session.session_id)
    restored_result = await manager.build_for_model_result(
        FakeModelClient([]),
        restored.get_messages(),
        restored.get_compactions(),
    )
    assertions = (
        EvaluationAssertion(
            "compaction-created",
            first_result.compaction is not None,
            "超预算历史没有生成压缩记录",
        ),
        EvaluationAssertion(
            "session-restored",
            restored.get_compactions() == session.get_compactions(),
            "Session 恢复后压缩记录不一致",
        ),
        EvaluationAssertion(
            "context-restored",
            restored_result.messages == first_result.messages,
            "恢复后的模型上下文与压缩结果不一致",
        ),
    )
    return EvaluationResult(
        scenario=COMPACTION_RESTORE_SCENARIO.name,
        duration_ms=(perf_counter() - started_at) * 1000,
        model_requests=len(client.requests),
        compactions=int(first_result.compaction is not None),
        estimated_tokens=sum(
            estimate_context_tokens(request) for request in client.requests
        ),
        assertions=assertions,
    )
