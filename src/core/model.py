"""定义模型客户端与应用之间的最小接口。"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    """一次模型对话中的消息。"""

    role: MessageRole
    content: str


class ModelClientError(RuntimeError):
    """模型请求失败时向上层抛出的统一异常。"""


class ModelClient(Protocol):
    """所有模型客户端都需要实现的流式对话接口。"""

    async def stream_chat(
        self,
        messages: Sequence[Message],
    ) -> AsyncIterator[str]:
        """根据消息列表生成文本片段。"""
