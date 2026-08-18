"""实现模型和工具之间的最小执行循环。"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass

from .error_policy import AgentErrorPolicy
from .errors import AgentError
from .model import (
    Message,
    ModelClient,
    ModelEvent,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    ToolResult,
)
from .tools import ToolManager


@dataclass(frozen=True)
class ToolExecutionEvent:
    """表示一次工具调用已经完成。"""

    tool_call: ToolCall
    result: ToolResult


AgentEvent = ModelEvent | ToolExecutionEvent
EventHandler = Callable[[AgentEvent], Awaitable[None]]


@dataclass(frozen=True)
class AgentRunResult:
    """保存一轮 Agent Loop 的完整运行结果。"""

    messages: tuple[Message, ...]
    final_content: str


class AgentLoopError(RuntimeError):
    """Agent Loop 无法继续执行时抛出的异常。"""


class AgentLoop:
    """负责请求模型、执行工具并把结果继续交给模型。"""

    def __init__(
        self,
        client: ModelClient,
        tool_manager: ToolManager,
        max_tool_rounds: int = 10,
    ) -> None:
        """创建 Agent Loop，并设置单轮工具调用上限。"""

        self._client = client
        self._tool_manager = tool_manager
        self._max_tool_rounds = max_tool_rounds
        self._error_policy = AgentErrorPolicy()

    async def run(
        self,
        messages: Sequence[Message],
        on_event: EventHandler | None = None,
    ) -> AgentRunResult:
        """执行一轮模型—工具循环并返回完整上下文。"""

        context = list(messages)
        for _ in range(self._max_tool_rounds + 1):
            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            async for event in self._stream_model_events(
                context,
                tools=self._tool_manager.model_tools(),
            ):
                if on_event is not None:
                    await on_event(event)
                if isinstance(event, TextDelta):
                    text_parts.append(event.content)
                elif isinstance(event, ToolCallEvent):
                    tool_calls.append(event.tool_call)

            assistant_content = "".join(text_parts)
            context.append(
                Message(
                    role="assistant",
                    content=assistant_content,
                    tool_calls=tuple(tool_calls),
                )
            )
            if not tool_calls:
                return AgentRunResult(tuple(context), assistant_content)

            for tool_call in tool_calls:
                result = await self._tool_manager.execute(tool_call)
                context.append(
                    Message(
                        role="tool",
                        content=result.content,
                        tool_call_id=tool_call.call_id,
                    )
                )
                if on_event is not None:
                    await on_event(ToolExecutionEvent(tool_call, result))

        raise AgentLoopError("工具调用轮次超过限制")

    async def _stream_model_events(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ModelEvent]:
        """在不重复展示部分输出的前提下重试模型请求。"""

        attempt = 0
        while True:
            received_event = False
            try:
                async for event in self._client.stream_response(messages, tools=tools):
                    received_event = True
                    yield event
                return
            except AgentError as error:
                decision = self._error_policy.decide(error)
                if (
                    decision.action != "retry"
                    or received_event
                    or attempt >= decision.max_attempts
                ):
                    raise
                attempt += 1
                if decision.delay_seconds:
                    await asyncio.sleep(decision.delay_seconds)
