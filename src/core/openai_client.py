"""OpenAI-compatible 模型客户端实现。"""

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass

from openai import AsyncOpenAI

from .config import Settings
from .errors import ErrorCategory
from .model import (
    Message,
    ModelEvent,
    ModelClientError,
    TextDelta,
    ToolCall,
    ToolCallEvent,
)


@dataclass
class _ToolCallBuffer:
    """暂存流式工具调用的分片内容。"""

    call_id: str = ""
    name: str = ""
    arguments: str = ""


class OpenAICompatibleClient:
    """使用 OpenAI SDK 调用 OpenAI-compatible 服务。"""

    def __init__(
        self,
        settings: Settings,
        client: AsyncOpenAI | None = None,
    ) -> None:
        """根据配置创建客户端，也允许注入测试客户端。"""

        self._model_name = settings.model_name
        self._first_byte_timeout_seconds = settings.first_byte_timeout_seconds
        self._stream_idle_timeout_seconds = settings.stream_idle_timeout_seconds
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=max(
                self._first_byte_timeout_seconds,
                self._stream_idle_timeout_seconds,
            ),
        )

    async def stream_chat(
        self,
        messages: Sequence[Message],
    ) -> AsyncIterator[str]:
        """发送消息并逐段返回模型生成的文本。"""

        async for event in self.stream_response(messages):
            if isinstance(event, TextDelta):
                yield event.content

    async def stream_response(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] = (),
    ) -> AsyncIterator[ModelEvent]:
        """发送消息并解析文本和工具调用事件。"""

        request_messages = [_serialize_message(message) for message in messages]
        request: dict[str, object] = {
            "model": self._model_name,
            "messages": request_messages,
            "stream": True,
        }
        if tools:
            request["tools"] = list(tools)

        try:
            tool_calls: dict[int, _ToolCallBuffer] = {}
            async for chunk in self._stream_chunks(request):
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = delta.content
                if content:
                    yield TextDelta(content)
                for tool_call_delta in getattr(delta, "tool_calls", None) or ():
                    _append_tool_call_delta(tool_calls, tool_call_delta)

            for index in sorted(tool_calls):
                yield ToolCallEvent(_build_tool_call(tool_calls[index], index))
        except asyncio.CancelledError:
            raise
        except ModelClientError:
            raise
        except Exception as exc:
            raise _to_model_error(exc) from exc

    async def _stream_chunks(
        self,
        request: Mapping[str, object],
    ) -> AsyncIterator[object]:
        """按首包和分片空闲时间读取模型流。"""

        async with asyncio.timeout(self._first_byte_timeout_seconds):
            stream = await self._client.chat.completions.create(**request)
            iterator = stream.__aiter__()
            try:
                chunk = await anext(iterator)
            except StopAsyncIteration:
                return
        yield chunk

        while True:
            try:
                async with asyncio.timeout(self._stream_idle_timeout_seconds):
                    chunk = await anext(iterator)
            except StopAsyncIteration:
                return
            yield chunk


def _to_model_error(error: BaseException) -> ModelClientError:
    """将底层模型异常转换为统一类别和安全提示。"""

    error_name = type(error).__name__
    if isinstance(error, (ConnectionError, TimeoutError, asyncio.TimeoutError)) or error_name in {
        "APIConnectionError",
        "APITimeoutError",
    }:
        is_timeout = isinstance(error, (TimeoutError, asyncio.TimeoutError)) or error_name == "APITimeoutError"
        category: ErrorCategory = "timeout" if is_timeout else "network"
        message = "模型请求超时" if category == "timeout" else "模型网络请求失败"
        return ModelClientError(message, category=category, retryable=True, cause=error)
    if error_name == "RateLimitError":
        return ModelClientError("模型请求过于频繁", category="rate_limit", retryable=True, cause=error)
    if error_name in {"AuthenticationError", "PermissionDeniedError"}:
        return ModelClientError("模型认证失败，请检查密钥配置", category="authentication", cause=error)
    if error_name in {"BadRequestError", "UnprocessableEntityError"}:
        if _is_context_overflow_error(error):
            return ModelClientError(
                "模型上下文超出限制，正在压缩后重试",
                category="context_overflow",
                cause=error,
            )
        return ModelClientError("模型请求参数无效", category="invalid_request", cause=error)
    return ModelClientError("模型请求失败，请检查配置和网络连接", category="internal", cause=error)


def _is_context_overflow_error(error: BaseException) -> bool:
    """根据服务端结构化错误码识别上下文长度超限。"""

    return any(
        code in {
            "context_length_exceeded",
            "context_window_exceeded",
            "max_context_length_exceeded",
        }
        for code in _error_codes(error)
    )


def _error_codes(error: BaseException) -> tuple[str, ...]:
    """读取 SDK 异常中可用于分类的结构化错误码。"""

    values = [getattr(error, "code", None)]
    body = getattr(error, "body", None)
    if isinstance(body, Mapping):
        details = body.get("error")
        if isinstance(details, Mapping):
            values.extend((details.get("code"), details.get("type")))
    return tuple(
        value.strip().lower()
        for value in values
        if isinstance(value, str) and value.strip()
    )


def _serialize_message(message: Message) -> dict[str, object]:
    """将内部消息转换为 OpenAI-compatible 消息。"""

    request: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        request["tool_calls"] = [
            {
                "id": tool_call.call_id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(
                        tool_call.arguments,
                        ensure_ascii=False,
                    ),
                },
            }
            for tool_call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        request["tool_call_id"] = message.tool_call_id
    return request


def _append_tool_call_delta(
    buffers: dict[int, _ToolCallBuffer],
    delta: object,
) -> None:
    """将一个 OpenAI 工具调用分片追加到对应缓冲区。"""

    index = getattr(delta, "index", 0)
    buffer = buffers.setdefault(index, _ToolCallBuffer())
    call_id = getattr(delta, "id", None)
    if call_id:
        buffer.call_id = call_id
    function = getattr(delta, "function", None)
    if function is None:
        return
    name = getattr(function, "name", None)
    if name:
        buffer.name = name
    arguments = getattr(function, "arguments", None)
    if arguments:
        buffer.arguments += arguments


def _build_tool_call(buffer: _ToolCallBuffer, index: int) -> ToolCall:
    """将工具调用缓冲区转换为已校验的内部对象。"""

    if not buffer.call_id or not buffer.name:
        raise ModelClientError(f"模型返回了不完整的工具调用：{index}")
    try:
        arguments = json.loads(buffer.arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ModelClientError("模型返回的工具参数不是有效 JSON") from exc
    if not isinstance(arguments, dict):
        raise ModelClientError("模型返回的工具参数必须是 JSON 对象")
    return ToolCall(
        call_id=buffer.call_id,
        name=buffer.name,
        arguments=arguments,
    )
