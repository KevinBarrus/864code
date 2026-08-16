from pathlib import Path

import pytest

from core import main
from core.config import Settings
from core.model import Message
from core.session_store import SessionStore


class FakePicker:
    """返回测试会话的选择器"""

    selected_id: str | None = None

    def __init__(self, summaries) -> None:
        """保存会话摘要"""

        self.summaries = summaries

    async def pick(self) -> str | None:
        """返回预设的会话 ID"""

        return self.selected_id


@pytest.mark.asyncio
async def test_run_resume_without_id_uses_picker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试不带 ID 的恢复流程会使用会话选择器"""

    monkeypatch.chdir(tmp_path)
    session_id = "11111111-1111-1111-1111-111111111111"
    store = SessionStore(tmp_path)
    store.append_message(session_id, Message(role="user", content="历史"))
    FakePicker.selected_id = session_id
    captured: dict[str, object] = {}

    async def fake_run_chat(client, status, workspace, restored_id) -> None:
        """记录应用启动参数"""

        captured["workspace"] = workspace
        captured["session_id"] = restored_id

    monkeypatch.setattr(main, "SessionPicker", FakePicker)
    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: Settings("https://example.com", "test", "key"),
    )
    monkeypatch.setattr(main, "run_chat", fake_run_chat)

    await main.run(resume=True)

    assert captured == {"workspace": tmp_path.resolve(), "session_id": session_id}


@pytest.mark.asyncio
async def test_run_resume_with_id_skips_picker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试带 ID 的恢复流程不会打开选择器"""

    monkeypatch.chdir(tmp_path)
    session_id = "22222222-2222-2222-2222-222222222222"
    picker_called = False
    captured: dict[str, object] = {}

    class UnexpectedPicker:
        """不应被调用的选择器"""

        def __init__(self, summaries) -> None:
            """记录错误调用"""

            nonlocal picker_called
            picker_called = True

        async def pick(self) -> str | None:
            """返回空结果"""

            return None

    async def fake_run_chat(client, status, workspace, restored_id) -> None:
        """记录应用启动参数"""

        captured["session_id"] = restored_id

    monkeypatch.setattr(main, "SessionPicker", UnexpectedPicker)
    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: Settings("https://example.com", "test", "key"),
    )
    monkeypatch.setattr(main, "run_chat", fake_run_chat)

    await main.run(session_id, resume=True)

    assert not picker_called
    assert captured == {"session_id": session_id}
