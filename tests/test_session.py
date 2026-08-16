import uuid
from pathlib import Path

from core.model import Message
from core.session import Session
from core.session_store import SessionStore


def test_new_sessions_have_unique_ids(tmp_path: Path) -> None:
    """测试新会话拥有合法且唯一的 Session ID"""

    first = Session(tmp_path)
    second = Session(tmp_path)

    assert uuid.UUID(first.session_id)
    assert first.session_id != second.session_id


def test_session_updates_memory_and_store(tmp_path: Path) -> None:
    """测试追加消息会同时更新内存和 JSONL 文件"""

    session = Session(tmp_path)
    expected = [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！"),
    ]

    session.add_user_message("你好")
    session.add_assistant_message("你好！")

    assert session.get_messages() == expected
    assert SessionStore(tmp_path).load_messages(session.session_id) == expected


def test_restore_rebuilds_session_memory(tmp_path: Path) -> None:
    """测试可以从 JSONL 恢复完整的会话记忆"""

    original = Session(tmp_path)
    original.add_user_message("第一次输入")
    original.add_assistant_message("第一次回复")

    restored = Session.restore(tmp_path, original.session_id)

    assert restored.session_id == original.session_id
    assert restored.get_messages() == [
        Message(role="user", content="第一次输入"),
        Message(role="assistant", content="第一次回复"),
    ]


def test_restored_session_can_continue_writing(tmp_path: Path) -> None:
    """测试恢复后的会话可以继续追加并持久化消息"""

    original = Session(tmp_path)
    original.add_user_message("之前的问题")

    restored = Session.restore(tmp_path, original.session_id)
    restored.add_assistant_message("之前的回答")

    assert SessionStore(tmp_path).load_messages(original.session_id) == [
        Message(role="user", content="之前的问题"),
        Message(role="assistant", content="之前的回答"),
    ]
