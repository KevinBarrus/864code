import logging
from pathlib import Path

import pytest

from core import main
from core.config import McpStdioSettings, Settings
from core.context import ContextBudget
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


def test_main_handles_unexpected_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """测试未知异常只展示简洁提示并保留调试异常链"""

    def raise_unexpected_error(coroutine) -> None:
        """模拟 asyncio 运行阶段发生未知异常"""

        coroutine.close()
        raise RuntimeError("unexpected")

    monkeypatch.setattr(main.asyncio, "run", raise_unexpected_error)
    with caplog.at_level(logging.DEBUG, logger="core.main"):
        exit_code = main.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "运行错误：发生未预期错误，请重试或查看调试日志" in captured.err
    assert "Traceback" not in captured.err
    assert caplog.records[0].exc_info is not None


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

    async def fake_run_chat(
        client,
        status,
        workspace,
        restored_id,
        context_budget,
        mcp_provider=None,
        max_tool_rounds=None,
    ) -> None:
        """记录应用启动参数"""

        captured["workspace"] = workspace
        captured["session_id"] = restored_id
        captured["context_budget"] = context_budget
        captured["max_tool_rounds"] = max_tool_rounds

    monkeypatch.setattr(main, "SessionPicker", FakePicker)
    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: Settings("https://example.com", "test", "key"),
    )
    monkeypatch.setattr(main, "run_chat", fake_run_chat)

    await main.run(resume=True)

    assert captured == {
        "workspace": tmp_path.resolve(),
        "session_id": session_id,
        "context_budget": ContextBudget(100_000, 16_000, 20_000),
        "max_tool_rounds": 10,
    }


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

    async def fake_run_chat(
        client,
        status,
        workspace,
        restored_id,
        context_budget,
        mcp_provider=None,
        max_tool_rounds=None,
    ) -> None:
        """记录应用启动参数"""

        captured["session_id"] = restored_id
        captured["context_budget"] = context_budget

    monkeypatch.setattr(main, "SessionPicker", UnexpectedPicker)
    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: Settings("https://example.com", "test", "key"),
    )
    monkeypatch.setattr(main, "run_chat", fake_run_chat)

    await main.run(session_id, resume=True)

    assert not picker_called
    assert captured == {
        "session_id": session_id,
        "context_budget": ContextBudget(100_000, 16_000, 20_000),
    }


@pytest.mark.asyncio
async def test_run_creates_configured_stdio_mcp_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试启动层会创建并传递已配置的 MCP Provider。"""

    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    class FakeProvider:
        """记录启动层传入的 MCP 配置。"""

        def __init__(self, command, provider_id, cwd) -> None:
            self.command = command
            self.provider_id = provider_id
            self.cwd = cwd

    async def fake_run_chat(
        client,
        status,
        workspace,
        restored_id,
        context_budget,
        mcp_provider=None,
        max_tool_rounds=None,
    ) -> None:
        """记录传入应用层的 Provider。"""

        captured["provider"] = mcp_provider

    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: Settings(
            "https://example.com",
            "test",
            "key",
            mcp_stdio=McpStdioSettings("node", ("server.js",), "demo"),
        ),
    )
    monkeypatch.setattr(main, "StdioMcpProvider", FakeProvider)
    monkeypatch.setattr(main, "run_chat", fake_run_chat)

    await main.run()

    provider = captured["provider"]
    assert isinstance(provider, FakeProvider)
    assert provider.command == ("node", "server.js")
    assert provider.provider_id == "demo"
    assert provider.cwd == tmp_path.resolve()
