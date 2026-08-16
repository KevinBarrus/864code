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


class ContextCompactionRequired(RuntimeError):
    """表示当前消息超出预算，需要先执行上下文压缩。"""


class ContextManager:
    """根据上下文预算生成模型请求消息。"""

    def __init__(self, budget: ContextBudget) -> None:
        """创建上下文管理器。"""

        self._budget = budget

    def build(self, messages: Sequence[Message]) -> list[Message]:
        """返回未超出预算的消息副本，超出预算时要求先压缩。"""

        message_list = list(messages)
        if estimate_context_tokens(message_list) > self._budget.compaction_threshold:
            raise ContextCompactionRequired("上下文超出预算，需要先执行压缩")
        return message_list


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
