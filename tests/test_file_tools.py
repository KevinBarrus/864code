from pathlib import Path

import pytest

from core.model import ToolCall
from core.tools import (
    ToolManager,
    WorkspacePathError,
    create_list_files_tool,
    create_read_file_tool,
    create_search_files_tool,
)


def _call(name: str, arguments: dict[str, object]) -> ToolCall:
    """构造测试用工具调用。"""

    return ToolCall(call_id="call-1", name=name, arguments=arguments)


def _manager(
    workspace: Path,
    *tools: tuple,
) -> ToolManager:
    """注册指定的本地文件工具。"""

    manager = ToolManager()
    for definition, handler in tools:
        manager.register_local(definition, handler)
    return manager


@pytest.mark.asyncio
async def test_read_file_returns_complete_text(tmp_path: Path) -> None:
    """测试读取工具返回完整文件内容。"""

    (tmp_path / "README.md").write_text("第一行\n第二行", encoding="utf-8")
    manager = _manager(tmp_path, create_read_file_tool(tmp_path))

    result = await manager.execute(_call("read_file", {"path": "README.md"}))

    assert result.content == "第一行\n第二行"
    assert result.is_error is False


@pytest.mark.asyncio
async def test_list_files_returns_sorted_entries(tmp_path: Path) -> None:
    """测试目录列表按名称排序并标记子目录。"""

    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    (tmp_path / "a").mkdir()
    manager = _manager(tmp_path, create_list_files_tool(tmp_path))

    result = await manager.execute(_call("list_files", {}))

    assert result.content == "a/\nb.txt"


@pytest.mark.asyncio
async def test_search_files_returns_matching_lines(tmp_path: Path) -> None:
    """测试搜索工具返回文件路径、行号和匹配行。"""

    (tmp_path / "main.py").write_text("one\nneedle here\n", encoding="utf-8")
    (tmp_path / "other.txt").write_text("nothing\n", encoding="utf-8")
    manager = _manager(tmp_path, create_search_files_tool(tmp_path))

    result = await manager.execute(
        _call("search_files", {"pattern": "needle"})
    )

    assert result.content == "main.py:2: needle here"


@pytest.mark.asyncio
async def test_file_tools_reject_workspace_escape(tmp_path: Path) -> None:
    """测试文件工具拒绝访问工作区之外的路径。"""

    manager = _manager(tmp_path, create_read_file_tool(tmp_path))

    result = await manager.execute(_call("read_file", {"path": "../secret.txt"}))

    assert result.is_error is True
    assert "工作区内" in result.content


def test_workspace_path_resolver_rejects_absolute_escape(tmp_path: Path) -> None:
    """测试工作区路径解析器拒绝工作区之外的绝对路径。"""

    from core.tools import resolve_workspace_path

    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(tmp_path, "/tmp/secret.txt")
