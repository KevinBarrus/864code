"""提供模型上下文的 Token 估算和预算配置。"""

import json
from dataclasses import dataclass
from math import ceil
from collections.abc import AsyncIterator
from typing import Sequence

from .model import Message, ModelClient, ModelClientError
from .prompts import load_prompt
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


DEFAULT_CONTEXT_BUDGET = ContextBudget(100_000, 16_000, 20_000)


class ContextCompactionRequired(RuntimeError):
    """表示当前消息超出预算，需要先执行上下文压缩。"""


class ContextSummaryError(RuntimeError):
    """表示上下文摘要请求在重试后仍然失败。"""


@dataclass(frozen=True)
class ContextBuildResult:
    """保存模型上下文及本次新生成的压缩记录。"""

    messages: list[Message]
    compaction: CompactionRecord | None = None
    fallback_used: bool = False


SUMMARY_SECTIONS = (
    "## Goal",
    "## Progress",
    "## Key Decisions",
    "## Next Steps",
    "## Critical Context",
)

SUMMARY_SYSTEM_PROMPT = load_prompt("context_summary")
SUMMARY_RETRY_SYSTEM_PROMPT = load_prompt("context_summary_retry")

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

        result = await self.build_for_model_result(client, messages, compactions)
        return result.messages

    async def build_for_model_result(
        self,
        client: ModelClient,
        messages: Sequence[Message],
        compactions: Sequence[CompactionRecord] = (),
    ) -> ContextBuildResult:
        """构建模型上下文，并返回成功生成的压缩记录。"""

        original_messages = list(messages)
        messages = _apply_latest_compaction(original_messages, compactions)
        try:
            return ContextBuildResult(self.build(messages))
        except ContextCompactionRequired:
            recent = select_recent_messages(messages, self._budget.keep_recent_tokens)
            oversized_prefix, oversized_suffix = _split_oversized_latest_turn(
                messages,
                self._budget.keep_recent_tokens,
            )
            if oversized_prefix:
                system_messages = [
                    message for message in messages if message.role == "system"
                ]
                latest_group_ids = {id(message) for message in oversized_prefix + oversized_suffix}
                old_messages = [
                    message
                    for message in messages
                    if message.role != "system" and id(message) not in latest_group_ids
                ]
                try:
                    # 先摘要历史，再摘要当前超大轮次的前缀
                    summaries = []
                    history = _summary_source(old_messages, compactions)
                    if history:
                        summaries.append(await generate_context_summary(client, history))
                    summaries.append(
                        await generate_context_summary(client, oversized_prefix)
                    )
                except ContextSummaryError:
                    return ContextBuildResult(self.build_fallback(messages), fallback_used=True)

                summary = "\n\n".join(summaries)
                summary_message = Message(
                    role="system",
                    content=f"Conversation summary:\n{summary}",
                )
                compacted_messages = system_messages + [summary_message] + oversized_suffix
                try:
                    self.build(compacted_messages)
                except ContextCompactionRequired:
                    return ContextBuildResult(self.build_fallback(messages), fallback_used=True)
                compaction = CompactionRecord(
                    summary=summary,
                    first_kept_message_index=_first_message_index(
                        original_messages,
                        oversized_suffix,
                    ),
                    tokens_before=estimate_context_tokens(messages),
                )
                return ContextBuildResult(compacted_messages, compaction)

            recent_conversation = [
                message for message in recent if message.role != "system"
            ]
            all_conversation = [
                message for message in messages if message.role != "system"
            ]
            omitted_count = len(all_conversation) - len(recent_conversation)
            if omitted_count <= 0:
                return ContextBuildResult(self.build_fallback(messages), fallback_used=True)

            omitted = all_conversation[:omitted_count]
            try:
                summary = await generate_context_summary(
                    client,
                    _summary_source(omitted, compactions),
                )
            except ContextSummaryError:
                return ContextBuildResult(self.build_fallback(messages), fallback_used=True)

            system_messages = [
                message for message in messages if message.role == "system"
            ]
            summary_message = Message(
                role="system",
                content=f"Conversation summary:\n{summary}",
            )
            first_kept_message_index = _first_message_index(
                original_messages,
                recent_conversation,
            )
            compaction = CompactionRecord(
                summary=summary,
                first_kept_message_index=first_kept_message_index,
                tokens_before=estimate_context_tokens(messages),
            )
            compacted_messages = system_messages + [summary_message] + recent_conversation
            try:
                self.build(compacted_messages)
            except ContextCompactionRequired:
                return ContextBuildResult(self.build_fallback(messages), fallback_used=True)
            return ContextBuildResult(compacted_messages, compaction)


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


def _summary_source(
    messages: Sequence[Message],
    compactions: Sequence[CompactionRecord],
) -> list[Message]:
    """组合上一次摘要和本次新增的旧消息，作为累计摘要输入。"""

    if not compactions:
        return list(messages)
    previous_summary = Message(
        role="system",
        content=f"Previous conversation summary:\n{compactions[-1].summary}",
    )
    return [previous_summary, *messages]


def _first_message_index(
    messages: Sequence[Message],
    selected_messages: Sequence[Message],
) -> int:
    """查找最近原始消息在完整历史中的起始序号。"""

    if not selected_messages:
        return len(messages)
    selected_ids = {id(message) for message in selected_messages}
    for index, message in enumerate(messages):
        if id(message) in selected_ids:
            return index
    return len(messages)


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


def _split_oversized_latest_turn(
    messages: Sequence[Message],
    max_tokens: int,
) -> tuple[list[Message], list[Message]]:
    """将超出最近预算的最新轮次拆为前缀和后缀。"""

    conversation_messages = [
        message for message in messages if message.role != "system"
    ]
    groups = _conversation_groups(conversation_messages)
    if not groups:
        return [], []

    latest_group = groups[-1]
    if estimate_context_tokens(latest_group) <= max_tokens:
        return [], latest_group

    for start in range(len(latest_group) - 1, -1, -1):
        suffix = latest_group[start:]
        if (
            estimate_context_tokens(suffix) <= max_tokens
            and _has_valid_tool_chain(suffix)
        ):
            return latest_group[:start], suffix
    return latest_group[:-1], latest_group[-1:]


def _has_valid_tool_chain(messages: Sequence[Message]) -> bool:
    """检查保留后缀中的工具调用链是否完整。"""

    call_ids = {
        tool_call.call_id
        for message in messages
        if message.role == "assistant"
        for tool_call in message.tool_calls
    }
    result_ids = {
        message.tool_call_id
        for message in messages
        if message.role == "tool" and message.tool_call_id is not None
    }
    return result_ids <= call_ids and call_ids <= result_ids


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
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        summary_messages = [
            Message(
                role="system",
                content=(
                    SUMMARY_SYSTEM_PROMPT
                    if attempt == 0
                    else SUMMARY_RETRY_SYSTEM_PROMPT
                ),
            ),
            Message(role="user", content=f"<conversation>\n{prompt}\n</conversation>"),
        ]
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
