"""提供模型上下文的 Token 估算和预算配置。"""

import json
from dataclasses import dataclass
from math import ceil
from typing import Sequence

from .model import Message


@dataclass(frozen=True)
class ContextBudget:
    """描述一次模型请求可使用的上下文预算。"""

    context_window: int
    reserve_tokens: int
    keep_recent_tokens: int

    def __post_init__(self) -> None:
        """校验上下文预算参数。"""

        if self.context_window <= 0:
            raise ValueError("上下文窗口必须大于 0")
        if self.reserve_tokens < 0 or self.reserve_tokens >= self.context_window:
            raise ValueError("回复预留 Token 必须小于上下文窗口")
        if self.keep_recent_tokens <= 0:
            raise ValueError("最近消息预算必须大于 0")

    @property
    def compaction_threshold(self) -> int:
        """返回触发上下文压缩的 Token 阈值。"""

        return self.context_window - self.reserve_tokens


def estimate_message_tokens(message: Message) -> int:
    """使用字符数估算单条消息的 Token 数。"""

    content_chars = len(message.content)
    tool_call_chars = sum(
        len(tool_call.name)
        + len(tool_call.call_id)
        + len(json.dumps(tool_call.arguments, ensure_ascii=False, sort_keys=True))
        for tool_call in message.tool_calls
    )
    tool_call_id_chars = len(message.tool_call_id or "")
    return ceil((content_chars + tool_call_chars + tool_call_id_chars) / 4)


def estimate_context_tokens(messages: Sequence[Message]) -> int:
    """估算消息列表的总 Token 数。"""

    return sum(estimate_message_tokens(message) for message in messages)
