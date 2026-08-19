import pytest

from core.model import ToolCall
from core.tool_approval import APPROVAL_OPTIONS, COMMAND_APPROVAL_OPTIONS, ApprovalPrompt
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
async def test_approval_prompt_shows_full_command() -> None:
    """测试命令审批会展示将执行的完整命令。"""

    definition = ToolDefinition(
        name="run_command",
        description="执行命令",
        parameters={"type": "object"},
        source="local",
        permission="command",
        idempotent=False,
    )
    prompt = ApprovalPrompt(
        definition,
        ToolCall("call-1", "run_command", {"command": "git status && pytest -q"}),
    )

    text = "".join(content for _, content in prompt._render())

    assert "Command: git status && pytest -q" in text


@pytest.mark.asyncio
async def test_approval_prompt_summarizes_file_content() -> None:
    """测试文件审批会展示路径和受限内容摘要。"""

    prompt = ApprovalPrompt(
        _definition(),
        ToolCall("call-1", "write_file", {"path": "src/app.py", "content": "x" * 200}),
    )

    text = "".join(content for _, content in prompt._render())

    assert "Path: src/app.py" in text
    assert "content: " in text
    assert "(200 chars)" in text


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
async def test_command_approval_omits_session_option() -> None:
    """测试不允许会话授权时只展示单次确认和拒绝。"""

    prompt = ApprovalPrompt(
        _definition(),
        ToolCall("call-1", "run_command", {"command": "pwd"}),
        allow_session=False,
    )
    text = "".join(content for _, content in prompt._render())

    assert all(option in text for option in COMMAND_APPROVAL_OPTIONS)
    assert APPROVAL_OPTIONS[1] not in text
    prompt.move(1)
    prompt.confirm()
    assert prompt._result.result().decision == ApprovalDecision.DENY


@pytest.mark.asyncio
async def test_approval_prompt_escape_returns_denial() -> None:
    """测试取消审批返回拒绝结果。"""

    prompt = _prompt()
    prompt.reject()

    assert prompt._result.result().decision == ApprovalDecision.DENY
