"""定义可重复执行的离线评测场景"""

from time import perf_counter

from core.agent_loop import AgentLoop, ToolExecutionEvent
from core.context import estimate_context_tokens
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
