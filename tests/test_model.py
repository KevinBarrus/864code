from collections.abc import AsyncIterator, Sequence

import pytest

from core.model import Message, ModelClient


class FakeModelClient:
    """用于测试应用层是否只依赖 ModelClient 接口。"""

    async def stream_chat(
        self,
        messages: Sequence[Message],
    ) -> AsyncIterator[str]:
        """返回固定文本片段，模拟模型的流式响应。"""

        assert messages == [Message(role="user", content="你好")]
        yield "你"
        yield "好"


async def _collect(chunks: AsyncIterator[str]) -> str:
    """收集流式文本，模拟 UI 消费模型输出的方式。"""

    """收集流式文本，模拟 UI 消费模型输出的方式。"""

    result = ""
    async for chunk in chunks:
        result += chunk
    return result


@pytest.mark.asyncio
async def test_model_client_streams_text_chunks() -> None:
    """测试模型客户端接口可以被异步调用并消费流式文本。"""

    client: ModelClient = FakeModelClient()

    answer = await _collect(
        client.stream_chat([Message(role="user", content="你好")])
    )

    assert answer == "你好"
