import shlex
import sys
from pathlib import Path

import pytest

from core.model import ToolCall
from core.tools import (
    ApprovalDecision,
    ApprovalResult,
    PermissionManager,
    ToolManager,
    create_edit_file_tool,
    create_run_command_tool,
    create_write_file_tool,
)


def _call(name: str, arguments: dict[str, object]) -> ToolCall:
    """构造测试用工具调用。"""

    return ToolCall(call_id="call-1", name=name, arguments=arguments)


def _manager(*tools: tuple) -> ToolManager:
    """注册指定的本地工具。"""

    async def approve(definition, tool_call) -> ApprovalResult:
        return ApprovalResult(ApprovalDecision.ALLOW_ONCE)

    manager = ToolManager(permission_manager=PermissionManager(approve))
    for definition, handler in tools:
        manager.register_local(definition, handler)
    return manager


@pytest.mark.asyncio
async def test_write_file_is_idempotent(tmp_path: Path) -> None:
    """测试写入相同内容时不会重复改变文件。"""

    manager = _manager(create_write_file_tool(tmp_path))
    call = _call("write_file", {"path": "src/a.txt", "content": "内容"})

    first = await manager.execute(call)
    second = await manager.execute(call)

    assert first.content == "文件已写入"
    assert second.content == "文件内容已经是目标内容"
    assert (tmp_path / "src/a.txt").read_text(encoding="utf-8") == "内容"


@pytest.mark.asyncio
async def test_write_file_allows_empty_content(tmp_path: Path) -> None:
    """测试写入工具允许创建空文件。"""

    manager = _manager(create_write_file_tool(tmp_path))

    result = await manager.execute(
        _call("write_file", {"path": "empty.txt", "content": ""})
    )

    assert result.is_error is False
    assert (tmp_path / "empty.txt").read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_edit_file_requires_expected_old_content(tmp_path: Path) -> None:
    """测试编辑工具能正常修改、识别重复调用并拒绝状态冲突。"""

    path = tmp_path / "a.txt"
    path.write_text("旧内容", encoding="utf-8")
    manager = _manager(create_edit_file_tool(tmp_path))
    call = _call(
        "edit_file",
        {"path": "a.txt", "old_content": "旧内容", "new_content": "新内容"},
    )

    assert (await manager.execute(call)).content == "文件已编辑"
    assert (await manager.execute(call)).content == "文件内容已经是目标内容"

    path.write_text("外部修改", encoding="utf-8")
    conflict = await manager.execute(call)
    assert conflict.is_error is True
    assert "已变化" in conflict.content


@pytest.mark.asyncio
async def test_run_command_returns_stdout_and_exit_error(tmp_path: Path) -> None:
    """测试命令工具返回标准输出和非零退出错误。"""

    manager = _manager(create_run_command_tool(tmp_path))
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote('print(\"完成\")')}"
    result = await manager.execute(_call("run_command", {"command": command}))

    assert result.is_error is False
    assert result.content == "完成"
    assert (tmp_path / "created.txt").exists() is False


@pytest.mark.asyncio
async def test_run_command_marks_nonzero_exit_as_error(tmp_path: Path) -> None:
    """测试命令非零退出码会标记为错误。"""

    manager = _manager(create_run_command_tool(tmp_path))
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote('import sys; sys.exit(2)')}"

    result = await manager.execute(_call("run_command", {"command": command}))

    assert result.is_error is True
    assert "退出码：2" in result.content
