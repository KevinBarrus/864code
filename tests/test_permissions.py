import pytest

from core.model import ToolCall
from core.tools import PermissionDenied, PermissionManager, ToolDefinition


def _definition(permission: str) -> ToolDefinition:
    """构造测试用工具定义。"""

    return ToolDefinition(
        name="test_tool",
        description="测试工具",
        parameters={"type": "object"},
        source="local",
        permission=permission,  # type: ignore[arg-type]
        idempotent=permission == "read",
    )


def _call() -> ToolCall:
    """构造测试用工具调用。"""

    return ToolCall(call_id="call-1", name="test_tool", arguments={})


@pytest.mark.asyncio
async def test_read_tool_is_allowed_without_confirmation() -> None:
    """测试只读工具不需要外部确认。"""

    await PermissionManager().authorize(_definition("read"), _call())


@pytest.mark.asyncio
async def test_mutating_tool_is_denied_without_confirmation() -> None:
    """测试没有确认回调时拒绝有副作用的工具。"""

    with pytest.raises(PermissionDenied, match="需要用户确认"):
        await PermissionManager().authorize(_definition("write"), _call())


@pytest.mark.asyncio
async def test_confirmation_callback_receives_tool_context() -> None:
    """测试确认回调可以获取工具定义和调用参数。"""

    received: list[tuple[str, str]] = []

    async def approve(definition: ToolDefinition, tool_call: ToolCall) -> bool:
        received.append((definition.name, tool_call.call_id))
        return True

    await PermissionManager(approve).authorize(_definition("command"), _call())

    assert received == [("test_tool", "call-1")]


@pytest.mark.asyncio
async def test_rejected_confirmation_raises_permission_error() -> None:
    """测试确认回调拒绝时阻止工具执行。"""

    async def reject(definition: ToolDefinition, tool_call: ToolCall) -> bool:
        return False

    with pytest.raises(PermissionDenied, match="用户拒绝"):
        await PermissionManager(reject).authorize(_definition("write"), _call())
