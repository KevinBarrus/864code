import pytest

from core.model import ToolCall
from core.tools import (
    ApprovalDecision,
    ApprovalResult,
    PermissionDenied,
    PermissionManager,
    ToolDefinition,
)


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

    async def approve(
        definition: ToolDefinition,
        tool_call: ToolCall,
    ) -> ApprovalResult:
        received.append((definition.name, tool_call.call_id))
        return ApprovalResult(ApprovalDecision.ALLOW_ONCE)

    result = await PermissionManager(approve).authorize(_definition("command"), _call())

    assert received == [("test_tool", "call-1")]
    assert result.decision == ApprovalDecision.ALLOW_ONCE


@pytest.mark.asyncio
async def test_rejected_confirmation_returns_denial() -> None:
    """测试确认回调拒绝时返回拒绝结果。"""

    async def reject(
        definition: ToolDefinition,
        tool_call: ToolCall,
    ) -> ApprovalResult:
        return ApprovalResult(
            ApprovalDecision.DENY,
            feedback="先只读取文件",
        )

    result = await PermissionManager(reject).authorize(_definition("write"), _call())

    assert result == ApprovalResult(ApprovalDecision.DENY, "先只读取文件")


@pytest.mark.asyncio
async def test_session_grant_skips_future_confirmation() -> None:
    """测试当前 Session 授权后不再重复确认同一个工具。"""

    calls = 0

    async def approve(
        definition: ToolDefinition,
        tool_call: ToolCall,
    ) -> ApprovalResult:
        nonlocal calls
        calls += 1
        return ApprovalResult(ApprovalDecision.ALLOW_SESSION)

    manager = PermissionManager(approve)
    first = await manager.authorize(_definition("write"), _call())
    second = await manager.authorize(_definition("write"), _call())

    assert first.decision == ApprovalDecision.ALLOW_SESSION
    assert second.decision == ApprovalDecision.ALLOW_SESSION
    assert calls == 1
