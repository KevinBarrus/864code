"""提供不访问网络的模型和工具替身"""

from collections.abc import Sequence

from core.model import Message, ModelEvent, ToolCall, ToolResult


class FakeModelClient:
    """按预设脚本返回模型事件或抛出异常"""

    def __init__(
        self,
        responses: Sequence[Sequence[ModelEvent] | BaseException],
    ) -> None:
        """保存模型响应脚本和请求记录"""

        self._responses = list(responses)
        self.requests: list[list[Message]] = []
        self.tools: list[list[dict[str, object]]] = []

    async def stream_response(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, object]] = (),
    ):
        """记录请求并按顺序返回一组模型事件"""

        self.requests.append(list(messages))
        self.tools.append(list(tools))
        index = len(self.requests) - 1
        if index >= len(self._responses):
            raise AssertionError("FakeModelClient 缺少响应脚本")
        response = self._responses[index]
        if isinstance(response, BaseException):
            raise response
        for event in response:
            yield event


class FakeToolHandler:
    """按预设脚本返回工具结果或抛出异常"""

    def __init__(self, responses: Sequence[ToolResult | BaseException]) -> None:
        """保存工具响应脚本和调用记录"""

        self._responses = list(responses)
        self.calls: list[ToolCall] = []

    async def __call__(self, tool_call: ToolCall) -> ToolResult:
        """记录工具调用并返回下一条预设结果"""

        self.calls.append(tool_call)
        index = len(self.calls) - 1
        if index >= len(self._responses):
            raise AssertionError("FakeToolHandler 缺少响应脚本")
        response = self._responses[index]
        if isinstance(response, BaseException):
            raise response
        return response
