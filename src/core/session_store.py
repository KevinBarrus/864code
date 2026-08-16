"""负责会话消息的 JSONL 文件读写。"""

import json
import uuid
from pathlib import Path

from .model import Message


class SessionStoreError(ValueError):
    """会话文件格式或会话标识无效时抛出的异常。"""


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
        if role not in {"user", "assistant"}:
            raise SessionStoreError(f"第 {line_number} 行的角色无效")
        if not isinstance(content, str):
            raise SessionStoreError(f"第 {line_number} 行的内容无效")
        return Message(role=role, content=content)
