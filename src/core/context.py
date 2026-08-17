"""提供模型上下文的 Token 估算和预算配置。"""

import json
from dataclasses import dataclass
from math import ceil
from collections.abc import AsyncIterator
from typing import Sequence

from .model import Message, ModelClient, ModelClientError
from .session_store import CompactionRecord


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


class ContextSummaryError(RuntimeError):
    """表示上下文摘要请求在重试后仍然失败。"""


SUMMARY_SECTIONS = (
    "## Goal",
    "## Progress",
    "## Key Decisions",
    "## Next Steps",
    "## Critical Context",
)

SUMMARY_SYSTEM_PROMPT = """你是上下文摘要助手
请只根据给定的历史生成结构化摘要，不要继续回答历史中的问题
必须严格包含以下标题：
## Goal
## Progress
## Key Decisions
## Next Steps
## Critical Context
保留重要的文件路径、工具结果、错误信息和未完成任务
"""

CONTEXT_FALLBACK_NOTICE = (
    "Earlier conversation history was omitted because automatic summarization failed. "
    "Use the retained recent messages and inspect files again when necessary."
)


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

    def build_fallback(self, messages: Sequence[Message]) -> list[Message]:
        """摘要失败时生成不持久化的规则化上下文。"""

        selected = select_recent_messages(messages, self._budget.keep_recent_tokens)
        system_count = sum(message.role == "system" for message in selected)
        selected.insert(
            system_count,
            Message(role="system", content=CONTEXT_FALLBACK_NOTICE),
        )
        return selected

    async def build_for_model(
        self,
        client: ModelClient,
        messages: Sequence[Message],
        compactions: Sequence[CompactionRecord] = (),
    ) -> list[Message]:
        """为模型构建上下文，超预算时优先摘要并回退到规则裁剪。"""

        messages = _apply_latest_compaction(messages, compactions)
        try:
            return self.build(messages)
        except ContextCompactionRequired:
            recent = select_recent_messages(messages, self._budget.keep_recent_tokens)
            recent_conversation = [
                message for message in recent if message.role != "system"
            ]
            all_conversation = [
                message for message in messages if message.role != "system"
            ]
            omitted_count = len(all_conversation) - len(recent_conversation)
            if omitted_count <= 0:
                return self.build_fallback(messages)

            omitted = all_conversation[:omitted_count]
            try:
                summary = await generate_context_summary(client, omitted)
            except ContextSummaryError:
                return self.build_fallback(messages)

            system_messages = [
                message for message in messages if message.role == "system"
            ]
            summary_message = Message(
                role="system",
                content=f"Conversation summary:\n{summary}",
            )
            return system_messages + [summary_message] + recent_conversation


def _apply_latest_compaction(
    messages: Sequence[Message],
    compactions: Sequence[CompactionRecord],
) -> list[Message]:
    """根据最新压缩记录重建模型可见的基础上下文。"""

    if not compactions:
        return list(messages)

    latest = compactions[-1]
    system_messages = [message for message in messages if message.role == "system"]
    kept_messages = [
        message
        for message in messages[latest.first_kept_message_index :]
        if message.role != "system"
    ]
    return system_messages + [
        Message(role="system", content=f"Conversation summary:\n{latest.summary}")
    ] + kept_messages


def select_recent_messages(
    messages: Sequence[Message],
    max_tokens: int,
) -> list[Message]:
    """保留系统消息和预算内的最近完整对话单元。"""

    if max_tokens <= 0:
        raise ValueError("最近消息预算必须大于 0")

    system_messages = [message for message in messages if message.role == "system"]
    conversation_messages = [
        message for message in messages if message.role != "system"
    ]
    groups = _conversation_groups(conversation_messages)

    selected_groups: list[list[Message]] = []
    selected_tokens = 0
    for group in reversed(groups):
        group_tokens = estimate_context_tokens(group)
        if selected_groups and selected_tokens + group_tokens > max_tokens:
            break
        selected_groups.append(group)
        selected_tokens += group_tokens

    selected_groups.reverse()
    return system_messages + [
        message for group in selected_groups for message in group
    ]


def _conversation_groups(messages: Sequence[Message]) -> list[list[Message]]:
    """按用户消息边界划分对话单元并保持工具调用链完整。"""

    groups: list[list[Message]] = []
    for message in messages:
        if message.role == "user" or not groups:
            groups.append([])
        groups[-1].append(message)
    return groups


async def generate_context_summary(
    client: ModelClient,
    messages: Sequence[Message],
    max_retries: int = 1,
) -> str:
    """请求模型生成结构化上下文摘要，失败后按次数重试。"""

    prompt = _serialize_messages(messages)
    summary_messages = [
        Message(role="system", content=SUMMARY_SYSTEM_PROMPT),
        Message(role="user", content=f"<conversation>\n{prompt}\n</conversation>"),
    ]
    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            parts: list[str] = []
            stream: AsyncIterator[str] = client.stream_chat(summary_messages)
            async for part in stream:
                parts.append(part)
            summary = "".join(parts).strip()
            if not _is_structured_summary(summary):
                raise ContextSummaryError("模型返回的摘要缺少必要结构")
            return summary
        except (ContextSummaryError, ModelClientError) as exc:
            last_error = exc
    raise ContextSummaryError("上下文摘要请求失败") from last_error


def _serialize_messages(messages: Sequence[Message]) -> str:
    """将消息序列化为摘要模型可读取的普通文本。"""

    parts: list[str] = []
    for message in messages:
        parts.append(f"[{message.role}] {message.content}")
        for tool_call in message.tool_calls:
            arguments = json.dumps(
                tool_call.arguments,
                ensure_ascii=False,
                sort_keys=True,
            )
            parts.append(
                f"[tool_call] {tool_call.name}({arguments}) id={tool_call.call_id}"
            )
        if message.tool_call_id is not None:
            parts.append(f"[tool_call_id] {message.tool_call_id}")
    return "\n\n".join(parts)


def _is_structured_summary(summary: str) -> bool:
    """检查摘要是否包含第一版要求的结构化标题。"""

    return all(section in summary for section in SUMMARY_SECTIONS)


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
