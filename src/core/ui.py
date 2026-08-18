"""实现全屏终端对话界面"""

import asyncio
from pathlib import Path

from .agent_loop import AgentLoop, AgentLoopError
from .errors import AgentError
from .screen import ChatScreen
from .status import StatusInfo
from .agent_loop import ToolExecutionEvent
from .model import Message, ModelClient, TextDelta, ToolCallEvent
from .context import ContextBudget, ContextManager, DEFAULT_CONTEXT_BUDGET
from .session import Session
from .tools import (
    PermissionManager,
    ToolManager,
    create_edit_file_tool,
    create_list_files_tool,
    create_read_file_tool,
    create_run_command_tool,
    create_search_files_tool,
    create_write_file_tool,
)


async def run_chat(
    client: ModelClient,
    status: StatusInfo,
    workspace: Path | None = None,
    session_id: str | None = None,
    context_budget: ContextBudget | None = None,
) -> None:
    """启动全屏界面，并处理模型的流式回复"""

    screen: ChatScreen
    session_workspace = (workspace or Path.cwd()).resolve()
    session = (
        Session.restore(session_workspace, session_id)
        if session_id
        else Session(session_workspace)
    )

    async def handle_submit(prompt: str) -> None:
        """发送请求，并同步当前会话的消息历史"""

        # 先更新界面，让用户立即看到本轮输入和待生成的回复区域
        screen.add_entry("user", prompt)
        response_index = screen.add_entry("assistant", "")
        response_parts: list[str] = []
        tool_activity_indices: dict[str, int] = {}
        awaiting_response_after_tool = False

        # 用户消息必须先进入会话，模型才能在本轮请求中看到它
        session.add_user_message(prompt)

        async def handle_event(event) -> None:
            """将模型事件转换为回复文本或简短工具活动条目。"""

            nonlocal response_index, awaiting_response_after_tool

            if isinstance(event, TextDelta):
                if awaiting_response_after_tool:
                    response_index = screen.add_entry("assistant", "")
                    awaiting_response_after_tool = False
                response_parts.append(event.content)
                screen.append_to_entry(response_index, event.content)
            elif isinstance(event, ToolCallEvent):
                summary = _tool_call_summary(event.tool_call)
                tool_activity_indices[event.tool_call.call_id] = screen.add_entry(
                    "tool",
                    summary,
                )
                awaiting_response_after_tool = True
            elif isinstance(event, ToolExecutionEvent):
                index = tool_activity_indices.get(event.tool_call.call_id)
                if index is not None:
                    screen.set_entry_content(index, _tool_result_summary(event))

        try:
            # 由 Agent Loop 负责模型与工具循环，界面只消费文本事件
            context_result = await context_manager.build_for_model_result(
                client,
                session.get_messages(),
                session.get_compactions(),
            )
            if context_result.compaction is not None:
                session.add_compaction(context_result.compaction)
            if context_result.fallback_used:
                screen.add_entry(
                    "tool",
                    "⚠ Context summary failed; recent history only",
                )
            result = await agent_loop.run(context_result.messages, on_event=handle_event)
        except asyncio.CancelledError:
            # 取消时保留已生成的部分回复，供下一轮继续参考
            response = "".join(response_parts)
            if response:
                session.add_message(
                    Message(
                        role="assistant",
                        content=response,
                        status="cancelled",
                    )
                )
            screen.append_to_entry(response_index, "（已取消）")
            raise
        except (AgentError, AgentLoopError) as exc:
            # 模型请求失败时保留部分回复和结构化错误状态
            response = "".join(response_parts)
            session.add_message(
                Message(
                    role="assistant",
                    content=response,
                    status="error",
                    error_category=(
                        exc.category if isinstance(exc, AgentError) else "internal"
                    ),
                )
            )
            screen.append_to_entry(response_index, f"错误：{exc}")
        else:
            # 流式响应完成后，按 AgentLoop 返回顺序保存本轮新增消息
            _persist_new_messages(session, result.messages)
            _update_persistence_status(screen, session)

    screen = ChatScreen(status, on_submit=handle_submit)
    tool_manager = ToolManager(
        permission_manager=PermissionManager(screen.request_approval),
    )
    for create_tool in (
        create_read_file_tool,
        create_list_files_tool,
        create_search_files_tool,
        create_write_file_tool,
        create_edit_file_tool,
        create_run_command_tool,
    ):
        tool_manager.register_local(*create_tool(session_workspace))
    context_manager = ContextManager(
        context_budget or DEFAULT_CONTEXT_BUDGET,
        {
            definition.name: definition.capability
            for definition in tool_manager.list_definitions()
            if definition.capability is not None
        },
    )
    agent_loop = AgentLoop(client, tool_manager)

    history = session.get_messages()
    for message in history:
        screen.add_entry(message.role, message.content)
    if history:
        screen.conversation_view.scroll_to_bottom()
    try:
        await screen.application.run_async()
    finally:
        if not session.close():
            screen.set_status_message("Session persistence degraded")


def _tool_call_summary(tool_call) -> str:
    """生成工具调用开始时的单行摘要。"""

    arguments = _single_line(str(tool_call.arguments), 60)
    return f"▸ {tool_call.name}  {arguments}"


def _persist_new_messages(session: Session, messages: tuple[Message, ...]) -> None:
    """只将 AgentLoop 本轮新增消息追加到 Session。"""

    existing_count = len(session.get_messages())
    for message in messages[existing_count:]:
        session.add_message(message)


def _tool_result_summary(event: ToolExecutionEvent) -> str:
    """生成工具执行完成时的单行摘要。"""

    marker = "✗" if event.result.is_error else "✓"
    content = _single_line(event.result.content, 60)
    return f"{marker} {event.tool_call.name}  {content}"


def _update_persistence_status(screen: ChatScreen, session: Session) -> None:
    """在持久化降级后向状态栏写入安全提示。"""

    if session.persistence_degraded:
        screen.set_status_message("Session persistence degraded")


def _single_line(content: str, limit: int) -> str:
    """压缩换行文本并限制界面摘要长度。"""

    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"
