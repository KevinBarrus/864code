from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from core import ui
from core.model import Message
from core.session import Session
from core.status import create_status_info
from core.tools import ApprovalDecision, ApprovalResult


class FakeApplication:
    """模拟 TUI 应用的启动"""

    async def run_async(self) -> None:
        """不启动真实终端"""


class FakeConversationView:
    """模拟对话滚动视图"""

    def __init__(self) -> None:
        """初始化滚动状态"""

        self.scrolled_to_bottom = False

    def scroll_to_bottom(self) -> None:
        """记录滚动到底部"""

        self.scrolled_to_bottom = True


class FakeScreen:
    """记录恢复时的历史展示内容"""

    last: "FakeScreen | None" = None

    def __init__(self, status, on_submit) -> None:
        """初始化假的界面对象"""

        self.entries: list[tuple[str, str]] = []
        self.conversation_view = FakeConversationView()
        self.application = FakeApplication()
        FakeScreen.last = self

    def add_entry(self, role: str, content: str) -> int:
        """记录一条展示消息"""

        self.entries.append((role, content))
        return len(self.entries) - 1

    async def request_approval(self, definition, tool_call, allow_session=True) -> ApprovalResult:
        """模拟界面审批回调"""

        return ApprovalResult(ApprovalDecision.ALLOW_ONCE)


class EmptyClient:
    """不产生新模型回复的测试客户端"""

    async def stream_chat(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """返回空的流式响应"""

        if False:
            yield ""


@pytest.mark.asyncio
async def test_run_chat_renders_restored_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试恢复会话时历史消息会立即展示并滚动到底部"""

    session = Session(tmp_path)
    session.add_user_message("历史问题")
    session.add_assistant_message("历史回答")
    assert session.flush_persistence()
    monkeypatch.setattr(ui, "ChatScreen", FakeScreen)

    await ui.run_chat(
        EmptyClient(),
        create_status_info("test", "暂不可查询", tmp_path),
        tmp_path,
        session.session_id,
    )

    assert FakeScreen.last is not None
    assert FakeScreen.last.entries == [
        ("user", "历史问题"),
        ("assistant", "历史回答"),
    ]
    assert FakeScreen.last.conversation_view.scrolled_to_bottom
