from core.model import ToolCall
from core.tool_approval import confirm_tool_call
from core.tools import ToolDefinition
import pytest


def _definition() -> ToolDefinition:
    """构造测试用工具定义。"""

    return ToolDefinition(
        name="write_file",
        description="写入文件",
        parameters={"type": "object"},
        source="local",
        permission="write",
        idempotent=True,
    )


@pytest.mark.asyncio
async def test_confirm_tool_call_accepts_yes(monkeypatch) -> None:
    """测试终端确认回调可以接受用户确认。"""

    async def fake_run_in_terminal(function, **kwargs):
        return "y"

    monkeypatch.setattr("core.tool_approval.run_in_terminal", fake_run_in_terminal)

    result = await confirm_tool_call(
        _definition(),
        ToolCall("call-1", "write_file", {"path": "a.txt"}),
    )

    assert result is True


@pytest.mark.asyncio
async def test_confirm_tool_call_rejects_other_input(monkeypatch) -> None:
    """测试终端确认回调默认拒绝其它输入。"""

    async def fake_run_in_terminal(function, **kwargs):
        return "n"

    monkeypatch.setattr("core.tool_approval.run_in_terminal", fake_run_in_terminal)

    result = await confirm_tool_call(
        _definition(),
        ToolCall("call-1", "write_file", {"path": "a.txt"}),
    )

    assert result is False
