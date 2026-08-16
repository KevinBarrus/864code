"""负责会话消息的 JSONL 文件读写。"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .model import Message, ToolCall


class SessionStoreError(ValueError):
    """会话文件格式或会话标识无效时抛出的异常。"""


@dataclass(frozen=True)
class SessionSummary:
    """用于会话选择器展示的最小摘要"""

    session_id: str
    title: str
    updated_at: datetime


class SessionStore:
    """将一个工作区中的会话消息追加或读取为 JSONL。"""

    def __init__(self, workspace: Path) -> None:
        """记录工作区路径，不提前创建运行时目录。"""

        self._sessions_dir = workspace / ".864code" / "sessions"

    def append_message(self, session_id: str, message: Message) -> None:
        """将一条消息追加到指定会话的 JSONL 文件。"""

        session_path = self._session_path(session_id)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "type": "message",
            "role": message.role,
            "content": message.content,
        }
        if message.tool_calls:
            record["tool_calls"] = [
                {
                    "call_id": tool_call.call_id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }
                for tool_call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            record["tool_call_id"] = message.tool_call_id
        with session_path.open("a", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False)
            file.write("\n")

    def load_messages(self, session_id: str) -> list[Message]:
        """按文件顺序读取指定会话的全部消息。"""

        session_path = self._session_path(session_id)
        if not session_path.exists():
            return []

        messages: list[Message] = []
        with session_path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SessionStoreError(
                        f"第 {line_number} 行不是有效 JSON"
                    ) from exc
                messages.append(self._message_from_record(record, line_number))
        return messages

    def list_sessions(self) -> list[SessionSummary]:
        """读取工作区中的会话摘要并按更新时间倒序排列"""

        if not self._sessions_dir.is_dir():
            return []

        summaries: list[SessionSummary] = []
        for session_path in self._sessions_dir.glob("*.jsonl"):
            session_id = session_path.stem
            try:
                messages = self.load_messages(session_id)
            except SessionStoreError as exc:
                raise SessionStoreError(
                    f"无法读取会话 {session_id}: {exc}"
                ) from exc

            summaries.append(
                SessionSummary(
                    session_id=session_id,
                    title=self._create_title(messages, session_id),
                    updated_at=datetime.fromtimestamp(
                        session_path.stat().st_mtime,
                        tz=timezone.utc,
                    ),
                )
            )
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    def _session_path(self, session_id: str) -> Path:
        """校验 Session ID 后生成对应文件路径。"""

        try:
            normalized_id = str(uuid.UUID(session_id))
        except (ValueError, AttributeError) as exc:
            raise SessionStoreError("无效的 Session ID") from exc
        return self._sessions_dir / f"{normalized_id}.jsonl"

    @staticmethod
    def _message_from_record(record: object, line_number: int) -> Message:
        """校验 JSON 记录并转换为模型消息。"""

        if not isinstance(record, dict) or record.get("type") != "message":
            raise SessionStoreError(f"第 {line_number} 行不是消息记录")

        role = record.get("role")
        content = record.get("content")
        if role not in {"user", "assistant", "tool"}:
            raise SessionStoreError(f"第 {line_number} 行的角色无效")
        if not isinstance(content, str):
            raise SessionStoreError(f"第 {line_number} 行的内容无效")

        raw_tool_calls = record.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            raise SessionStoreError(f"第 {line_number} 行的工具调用无效")
        tool_calls: list[ToolCall] = []
        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, dict):
                raise SessionStoreError(f"第 {line_number} 行的工具调用无效")
            call_id = raw_tool_call.get("call_id")
            name = raw_tool_call.get("name")
            arguments = raw_tool_call.get("arguments")
            if (
                not isinstance(call_id, str)
                or not isinstance(name, str)
                or not isinstance(arguments, dict)
            ):
                raise SessionStoreError(f"第 {line_number} 行的工具调用无效")
            tool_calls.append(ToolCall(call_id, name, arguments))

        tool_call_id = record.get("tool_call_id")
        if tool_call_id is not None and not isinstance(tool_call_id, str):
            raise SessionStoreError(f"第 {line_number} 行的工具调用 ID 无效")
        if role == "tool" and not tool_call_id:
            raise SessionStoreError(f"第 {line_number} 行缺少工具调用 ID")
        return Message(
            role=role,
            content=content,
            tool_calls=tuple(tool_calls),
            tool_call_id=tool_call_id,
        )

    @staticmethod
    def _create_title(messages: list[Message], session_id: str) -> str:
        """从第一条用户消息生成会话标题"""

        first_user_message = next(
            (message.content for message in messages if message.role == "user"),
            "",
        )
        title = " ".join(first_user_message.split())
        if not title:
            return session_id[:8]
        if len(title) <= 40:
            return title
        return f"{title[:37]}..."
