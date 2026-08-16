"""管理当前会话中的模型消息历史。"""

from .model import Message


class Memory:
    """保存一个会话的消息，不负责持久化或上下文裁剪。"""

    def __init__(self) -> None:
        """创建空的消息历史。"""

        self._messages: list[Message] = []

    def add_user_message(self, content: str) -> None:
        """追加一条用户消息。"""

        self.add_message(Message(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        """追加一条模型消息。"""

        self.add_message(Message(role="assistant", content=content))

    def add_message(self, message: Message) -> None:
        """追加一条完整消息，保留工具调用相关字段。"""

        self._messages.append(message)

    def get_messages(self) -> list[Message]:
        """返回消息历史副本，避免调用方直接修改内部列表。"""

        return list(self._messages)
