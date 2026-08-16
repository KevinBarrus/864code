import pytest

from core.model import ToolCall
from core.tool_approval import APPROVAL_OPTIONS, ApprovalPrompt
from core.tools import ApprovalDecision, ToolDefinition


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


def _prompt() -> ApprovalPrompt:
    """构造测试用审批面板。"""

    return ApprovalPrompt(
        _definition(),
        ToolCall("call-1", "write_file", {"path": "a.txt"}),
    )


@pytest.mark.asyncio
async def test_approval_prompt_moves_and_clamps_selection() -> None:
    """测试审批选项支持上下移动并限制边界。"""

    prompt = _prompt()

    prompt.move(-1)
    assert prompt.selected_index == 0

    prompt.move(10)
    assert prompt.selected_index == len(APPROVAL_OPTIONS) - 1

    prompt.move(-1)
    assert prompt.selected_index == len(APPROVAL_OPTIONS) - 2


@pytest.mark.asyncio
async def test_approval_prompt_marks_only_selected_option_blue() -> None:
    """测试渲染结果只给选中项使用蓝色样式。"""

    prompt = _prompt()
    fragments = prompt._render()

    selected = [text for style, text in fragments if style == "class:approval-selected"]

    assert selected == [f"> {APPROVAL_OPTIONS[0]}"]


@pytest.mark.asyncio
async def test_approval_prompt_confirms_session_permission() -> None:
    """测试审批面板可以返回当前 Session 授权结果。"""

    prompt = _prompt()
    prompt.selected_index = 1
    prompt.confirm()

    result = prompt._result.result()

    assert result.decision == ApprovalDecision.ALLOW_SESSION


@pytest.mark.asyncio
async def test_approval_prompt_escape_returns_denial() -> None:
    """测试取消审批返回拒绝结果。"""

    prompt = _prompt()
    prompt.reject()

    assert prompt._result.result().decision == ApprovalDecision.DENY
