"""实现第一批只读本地文件工具。"""

from pathlib import Path

from ..model import ToolCall, ToolResult
from .args import optional_path, string_argument
from .path_utils import resolve_workspace_path
from .types import ToolDefinition, ToolHandler


def create_read_file_tool(workspace: Path) -> tuple[ToolDefinition, ToolHandler]:
    """创建读取单个文件的工具。"""

    async def read_file(tool_call: ToolCall) -> ToolResult:
        path = resolve_workspace_path(workspace, string_argument(tool_call, "path"))
        if not path.is_file():
            raise ValueError("目标不是文件")
        return ToolResult(
            call_id=tool_call.call_id,
            content=path.read_text(encoding="utf-8"),
        )

    return (
        ToolDefinition(
            name="read_file",
            description="读取工作区内文件的完整文本内容",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            source="local",
            permission="read",
            idempotent=True,
        ),
        read_file,
    )


def create_list_files_tool(workspace: Path) -> tuple[ToolDefinition, ToolHandler]:
    """创建列出目录内容的工具。"""

    async def list_files(tool_call: ToolCall) -> ToolResult:
        path = resolve_workspace_path(workspace, optional_path(tool_call))
        if not path.is_dir():
            raise ValueError("目标不是目录")

        entries = sorted(path.iterdir(), key=lambda item: item.name)
        content = "\n".join(
            f"{entry.name}{'/' if entry.is_dir() else ''}" for entry in entries
        )
        return ToolResult(
            call_id=tool_call.call_id,
            content=content or "目录为空",
        )

    return (
        ToolDefinition(
            name="list_files",
            description="列出工作区内目录的直接内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                },
            },
            source="local",
            permission="read",
            idempotent=True,
        ),
        list_files,
    )


def create_search_files_tool(workspace: Path) -> tuple[ToolDefinition, ToolHandler]:
    """创建在工作区内按文本查找内容的工具。"""

    async def search_files(tool_call: ToolCall) -> ToolResult:
        pattern = string_argument(tool_call, "pattern")
        root = resolve_workspace_path(workspace, optional_path(tool_call))
        if not root.is_dir():
            raise ValueError("搜索范围不是目录")

        matches: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if pattern in line:
                    relative_path = path.relative_to(workspace.resolve())
                    matches.append(f"{relative_path}:{line_number}: {line}")

        return ToolResult(
            call_id=tool_call.call_id,
            content="\n".join(matches) or "没有找到匹配内容",
        )

    return (
        ToolDefinition(
            name="search_files",
            description="在工作区文件中按文本内容搜索",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "required": ["pattern"],
            },
            source="local",
            permission="read",
            idempotent=True,
        ),
        search_files,
    )
