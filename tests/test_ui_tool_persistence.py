from pathlib import Path

from core.model import Message, ToolCall
from core.session import Session
from core.ui import _persist_new_messages


def test_ui_persists_new_tool_messages_in_agent_order(tmp_path: Path) -> None:
    """测试应用层按 AgentLoop 顺序保存工具消息。"""

    session = Session(tmp_path)
    session.add_user_message("读取文件")
    new_messages = (
        Message(
            role="assistant",
            content="",
            tool_calls=(ToolCall("call-1", "read_file", {"path": "a.txt"}),),
        ),
        Message(role="tool", content="文件内容", tool_call_id="call-1"),
        Message(role="assistant", content="文件内容如下"),
    )

    _persist_new_messages(session, new_messages)

    assert session.get_messages() == [
        Message(role="user", content="读取文件"),
        *new_messages,
    ]
