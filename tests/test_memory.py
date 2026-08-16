from core.memory import Memory
from core.model import Message


def test_memory_starts_empty() -> None:
    """测试新会话没有消息。"""

    assert Memory().get_messages() == []


def test_memory_appends_messages_in_order() -> None:
    """测试用户消息和模型消息按追加顺序保存。"""

    memory = Memory()
    memory.add_user_message("你好")
    memory.add_assistant_message("你好，有什么可以帮你？")

    assert memory.get_messages() == [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好，有什么可以帮你？"),
    ]


def test_get_messages_returns_a_copy() -> None:
    """测试外部修改历史副本不会影响 Memory 内部数据。"""

    memory = Memory()
    memory.add_user_message("原始消息")
    messages = memory.get_messages()
    messages.clear()

    assert memory.get_messages() == [Message(role="user", content="原始消息")]
