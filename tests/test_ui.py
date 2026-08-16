import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from core.model import Message
from core.model import ModelClientError
from core.screen import ChatScreen
from core.session import Session
from core.status import create_status_info


class FakeClient:
    """记录提交的消息，并返回固定的模型回复"""

    def __init__(self) -> None:
        """初始化请求记录"""

        self.received: list[list[Message]] = []

    async def stream_chat(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """记录当前请求并返回一段测试文本"""

        self.received.append(list(messages))
        yield "测试回复"


@pytest.mark.asyncio
async def test_submit_handler_sends_conversation_history(tmp_path: Path) -> None:
    """测试连续请求会携带当前会话的完整历史"""

    client = FakeClient()
    session = Session(tmp_path)
    status = create_status_info("test-model", "暂不可查询", tmp_path)
    screen = ChatScreen(status)

    async def handle_submit(prompt: str) -> None:
        """模拟应用层同步记忆和界面的请求流程"""

        screen.add_entry("你", prompt)
        response_index = screen.add_entry("模型", "")
        session.add_user_message(prompt)
        response = ""
        async for chunk in client.stream_chat(session.get_messages()):
            response += chunk
            screen.append_to_entry(response_index, chunk)
        session.add_assistant_message(response)

    screen._on_submit = handle_submit
    await screen._submit("你好")
    await screen._submit("第二次输入")

    assert client.received == [
        [Message(role="user", content="你好")],
        [
            Message(role="user", content="你好"),
            Message(role="assistant", content="测试回复"),
            Message(role="user", content="第二次输入"),
        ],
    ]


class CancellingClient:
    """返回部分文本后取消请求的测试客户端"""

    def __init__(self) -> None:
        """初始化请求记录"""

        self.received: list[list[Message]] = []

    async def stream_chat(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """记录请求并在返回部分文本后触发取消"""

        self.received.append(list(messages))
        yield "部分回复"
        raise asyncio.CancelledError


class FailingClient:
    """请求时返回模型错误的测试客户端"""

    async def stream_chat(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """模拟模型请求失败"""

        raise ModelClientError("请求失败")
        yield ""


@pytest.mark.asyncio
async def test_cancelled_response_is_kept_in_memory(tmp_path: Path) -> None:
    """测试取消请求后已生成的部分回复会进入下一轮历史"""

    client = CancellingClient()
    session = Session(tmp_path)
    status = create_status_info("test-model", "暂不可查询", tmp_path)
    screen = ChatScreen(status)

    async def handle_submit(prompt: str) -> None:
        """模拟带取消处理的应用层请求流程"""

        screen.add_entry("你", prompt)
        response_index = screen.add_entry("模型", "")
        session.add_user_message(prompt)
        response = ""
        try:
            async for chunk in client.stream_chat(session.get_messages()):
                response += chunk
                screen.append_to_entry(response_index, chunk)
        except asyncio.CancelledError:
            if response:
                session.add_assistant_message(response)
            screen.append_to_entry(response_index, "（已取消）")
            raise

    screen._on_submit = handle_submit
    with pytest.raises(asyncio.CancelledError):
        await handle_submit("第一次输入")

    restored = Session.restore(tmp_path, session.session_id)
    assert restored.get_messages() == [
        Message(role="user", content="第一次输入"),
        Message(role="assistant", content="部分回复"),
    ]

    # 第二次请求仍然取消，但断言的是它收到的历史
    with pytest.raises(asyncio.CancelledError):
        await handle_submit("第二次输入")

    assert client.received[1] == [
        Message(role="user", content="第一次输入"),
        Message(role="assistant", content="部分回复"),
        Message(role="user", content="第二次输入"),
    ]


@pytest.mark.asyncio
async def test_model_error_is_not_saved_in_session(tmp_path: Path) -> None:
    """测试模型错误提示只展示，不写入会话历史"""

    client = FailingClient()
    session = Session(tmp_path)
    status = create_status_info("test-model", "暂不可查询", tmp_path)
    screen = ChatScreen(status)

    async def handle_submit(prompt: str) -> None:
        """模拟模型错误处理流程"""

        screen.add_entry("你", prompt)
        response_index = screen.add_entry("模型", "")
        session.add_user_message(prompt)
        try:
            async for chunk in client.stream_chat(session.get_messages()):
                screen.append_to_entry(response_index, chunk)
        except ModelClientError as exc:
            screen.append_to_entry(response_index, f"错误：{exc}")

    screen._on_submit = handle_submit
    await screen._submit("测试错误")

    assert session.get_messages() == [Message(role="user", content="测试错误")]
