from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.errors import AgentError
from core.model import Message, ModelClientError, TextDelta, ToolCall, ToolCallEvent
from core.openai_client import OpenAICompatibleClient


class FakeCompletions:
    def __init__(self, chunks: list[object]) -> None:
        """保存假的模型响应片段。"""

        self.chunks = chunks
        self.received: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> AsyncIterator[object]:
        """记录请求参数，并返回假的异步响应流。"""

        self.received = kwargs
        return FakeStream(self.chunks)


class FakeStream:
    def __init__(self, chunks: list[object]) -> None:
        """初始化异步响应流。"""

        self._chunks = iter(chunks)

    def __aiter__(self) -> "FakeStream":
        """返回异步迭代器本身。"""

        return self

    async def __anext__(self) -> object:
        """逐个返回预先准备好的响应片段。"""

        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeClient:
    def __init__(self, chunks: list[object]) -> None:
        """组装与 OpenAI SDK 结构相似的测试客户端。"""

        self.completions = FakeCompletions(chunks)
        self.chat = SimpleNamespace(completions=self.completions)


def _settings() -> Settings:
    """构造测试用模型配置。"""

    return Settings(
        base_url="https://example.com/v1",
        model_name="test-model",
        api_key="test-key",
    )


async def _collect(client: OpenAICompatibleClient) -> str:
    """收集客户端产生的全部文本片段。"""

    result = ""
    async for chunk in client.stream_chat([Message(role="user", content="你好")]):
        result += chunk
    return result


@pytest.mark.asyncio
async def test_client_sends_openai_compatible_request_and_streams_response() -> None:
    """测试客户端发送正确请求并返回流式文本。"""

    fake_sdk = FakeClient(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="你"))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="好"))]
            ),
        ]
    )
    client = OpenAICompatibleClient(_settings(), fake_sdk)  # type: ignore[arg-type]

    answer = await _collect(client)

    assert answer == "你好"
    assert fake_sdk.completions.received == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "你好"}],
        "stream": True,
    }


@pytest.mark.asyncio
async def test_client_skips_empty_stream_chunks() -> None:
    """测试客户端会跳过没有文本内容的响应片段。"""

    fake_sdk = FakeClient(
        [
            SimpleNamespace(choices=[]),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="完成"))]
            ),
        ]
    )
    client = OpenAICompatibleClient(_settings(), fake_sdk)  # type: ignore[arg-type]

    assert await _collect(client) == "完成"


@pytest.mark.asyncio
async def test_client_wraps_request_error() -> None:
    """测试底层请求异常会被转换为统一的模型异常。"""

    class FailingCompletions:
        async def create(self, **kwargs: object) -> AsyncIterator[object]:
            """模拟底层网络请求失败。"""

            raise ConnectionError("test failure")

    failing_sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=FailingCompletions())
    )
    client = OpenAICompatibleClient(_settings(), failing_sdk)  # type: ignore[arg-type]

    with pytest.raises(ModelClientError, match="模型网络请求失败") as error_info:
        await _collect(client)

    error = error_info.value
    assert isinstance(error, AgentError)
    assert error.category == "network"
    assert error.retryable


@pytest.mark.asyncio
async def test_client_classifies_timeout_error() -> None:
    """测试超时异常会被转换为可重试的统一错误。"""

    class TimeoutCompletions:
        async def create(self, **kwargs: object) -> AsyncIterator[object]:
            """模拟模型请求超时。"""

            raise TimeoutError("test timeout")

    timeout_sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=TimeoutCompletions())
    )
    client = OpenAICompatibleClient(_settings(), timeout_sdk)  # type: ignore[arg-type]

    with pytest.raises(ModelClientError) as error_info:
        await _collect(client)

    assert error_info.value.category == "timeout"
    assert error_info.value.retryable


@pytest.mark.asyncio
async def test_client_classifies_context_overflow_error() -> None:
    """测试服务端上下文超限会被单独分类。"""

    class BadRequestError(Exception):
        pass

    class FailingCompletions:
        async def create(self, **kwargs: object) -> AsyncIterator[object]:
            raise BadRequestError("maximum context length exceeded")

    failing_sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=FailingCompletions())
    )
    client = OpenAICompatibleClient(_settings(), failing_sdk)  # type: ignore[arg-type]

    with pytest.raises(ModelClientError) as error_info:
        await _collect(client)

    assert error_info.value.category == "context_overflow"


@pytest.mark.asyncio
async def test_client_classifies_openai_connection_error() -> None:
    """测试 OpenAI SDK 网络异常会被转换为 network 类别"""

    class APIConnectionError(Exception):
        pass

    class FailingCompletions:
        async def create(self, **kwargs: object) -> AsyncIterator[object]:
            """模拟 OpenAI SDK 网络连接失败"""

            raise APIConnectionError("connection failed")

    failing_sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=FailingCompletions())
    )
    client = OpenAICompatibleClient(_settings(), failing_sdk)  # type: ignore[arg-type]

    with pytest.raises(ModelClientError) as error_info:
        await _collect(client)

    assert error_info.value.category == "network"
    assert error_info.value.retryable


async def _collect_events(client: OpenAICompatibleClient) -> list[object]:
    """收集客户端产生的模型事件。"""

    events: list[object] = []
    async for event in client.stream_response(
        [Message(role="user", content="读取文件")],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取文件",
                    "parameters": {"type": "object"},
                },
            }
        ],
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_client_parses_text_and_streaming_tool_call() -> None:
    """测试客户端解析文本片段和分片工具调用。"""

    fake_sdk = FakeClient(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="开始"))]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call-1",
                                    function=SimpleNamespace(
                                        name="read_file",
                                        arguments='{"path":',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(
                                        name=None,
                                        arguments='"README.md"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            ),
        ]
    )
    client = OpenAICompatibleClient(_settings(), fake_sdk)  # type: ignore[arg-type]

    events = await _collect_events(client)

    assert events == [
        TextDelta("开始"),
        ToolCallEvent(
            tool_call=ToolCall(
                call_id="call-1",
                name="read_file",
                arguments={"path": "README.md"},
            )
        ),
    ]
    assert fake_sdk.completions.received is not None
    assert fake_sdk.completions.received["tools"]


@pytest.mark.asyncio
async def test_client_rejects_invalid_tool_arguments() -> None:
    """测试客户端拒绝无效的工具参数 JSON。"""

    fake_sdk = FakeClient(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call-1",
                                    function=SimpleNamespace(
                                        name="read_file",
                                        arguments="{invalid",
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )
        ]
    )
    client = OpenAICompatibleClient(_settings(), fake_sdk)  # type: ignore[arg-type]

    with pytest.raises(ModelClientError, match="工具参数不是有效 JSON"):
        await _collect_events(client)
