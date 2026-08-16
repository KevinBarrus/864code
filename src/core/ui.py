"""实现全屏终端对话界面"""

import asyncio
from pathlib import Path

from .agent_loop import AgentLoop, AgentLoopError
from .screen import ChatScreen
from .status import StatusInfo
from .model import ModelClient, ModelClientError, TextDelta
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
) -> None:
    """启动全屏界面，并处理模型的流式回复"""

    screen: ChatScreen
    session_workspace = (workspace or Path.cwd()).resolve()
    session = (
        Session.restore(session_workspace, session_id)
        if session_id
        else Session(session_workspace)
    )
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
    agent_loop = AgentLoop(client, tool_manager)

    async def handle_submit(prompt: str) -> None:
        """发送请求，并同步当前会话的消息历史"""

        # 先更新界面，让用户立即看到本轮输入和待生成的回复区域
        screen.add_entry("user", prompt)
        response_index = screen.add_entry("assistant", "")
        response_parts: list[str] = []

        # 用户消息必须先进入会话，模型才能在本轮请求中看到它
        session.add_user_message(prompt)

        async def handle_event(event) -> None:
            """将模型文本事件追加到当前回复，不处理工具展示。"""

            if isinstance(event, TextDelta):
                response_parts.append(event.content)
                screen.append_to_entry(response_index, event.content)

        try:
            # 由 Agent Loop 负责模型与工具循环，界面只消费文本事件
            await agent_loop.run(session.get_messages(), on_event=handle_event)
        except asyncio.CancelledError:
            # 取消时保留已生成的部分回复，供下一轮继续参考
            response = "".join(response_parts)
            if response:
                session.add_assistant_message(response)
            screen.append_to_entry(response_index, "（已取消）")
            raise
        except (ModelClientError, AgentLoopError) as exc:
            # 模型请求失败只展示错误，不把错误提示写入模型记忆
            screen.append_to_entry(response_index, f"错误：{exc}")
        else:
            # 流式响应完成后，再一次性保存完整的模型消息
            response = "".join(response_parts)
            if response:
                session.add_assistant_message(response)

    history = session.get_messages()
    for message in history:
        screen.add_entry(message.role, message.content)
    if history:
        screen.conversation_view.scroll_to_bottom()
    await screen.application.run_async()
