"""管理可持久化的单个 Coding Agent 会话"""

import uuid
from pathlib import Path

from .memory import Memory
from .model import Message
from .session_store import SessionStore


class Session:
    """组合会话标识、运行时记忆和 JSONL 存储"""

    def __init__(self, workspace: Path, session_id: str | None = None) -> None:
        """创建一个新会话，不读取已有文件"""

        self.workspace = workspace
        self.session_id = session_id or str(uuid.uuid4())
        self._memory = Memory()
        self._store = SessionStore(workspace)

    @classmethod
    def restore(cls, workspace: Path, session_id: str) -> "Session":
        """从已有 JSONL 文件恢复一个会话"""

        session = cls(workspace, session_id)
        for message in session._store.load_messages(session.session_id):
            session._add_to_memory(message)
        return session

    def add_user_message(self, content: str) -> None:
        """持久化并追加一条用户消息"""

        self._append_message(Message(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        """持久化并追加一条模型消息"""

        self._append_message(Message(role="assistant", content=content))

    def add_message(self, message: Message) -> None:
        """持久化并追加一条完整消息"""

        self._append_message(message)

    def get_messages(self) -> list[Message]:
        """返回当前会话的消息历史"""

        return self._memory.get_messages()

    def _append_message(self, message: Message) -> None:
        """先写入 JSONL，再更新内存，避免写入失败时状态不一致"""

        self._store.append_message(self.session_id, message)
        self._add_to_memory(message)

    def _add_to_memory(self, message: Message) -> None:
        """将已有消息按角色追加到运行时记忆"""

        self._memory.add_message(message)
