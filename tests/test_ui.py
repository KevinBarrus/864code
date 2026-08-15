from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from core.model import Message
from core.screen import ChatScreen
from core.status import create_status_info


class FakeClient:
    """记录提交的消息，并返回固定的模型回复。"""

    def __init__(self) -> None:
        """初始化请求记录。"""

        self.received: list[list[Message]] = []

    async def stream_chat(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """记录当前请求并返回一段测试文本。"""

        self.received.append(list(messages))
        yield "测试回复"


@pytest.mark.asyncio
async def test_submit_handler_sends_each_input_without_history(tmp_path: Path) -> None:
    """测试全屏界面每次只向模型发送当前输入。"""

    client = FakeClient()
    status = create_status_info("test-model", "暂不可查询", tmp_path)
    screen = ChatScreen(status)

    async def handle_submit(prompt: str) -> None:
        """模拟启动流程中的单轮模型请求。"""

        screen.add_entry("你", prompt)
        response_index = screen.add_entry("模型", "")
        async for chunk in client.stream_chat(
            [Message(role="user", content=prompt)]
        ):
            screen.append_to_entry(response_index, chunk)

    screen._on_submit = handle_submit
    await screen._submit("你好")
    await screen._submit("第二次输入")

    assert client.received == [
        [Message(role="user", content="你好")],
        [Message(role="user", content="第二次输入")],
    ]
