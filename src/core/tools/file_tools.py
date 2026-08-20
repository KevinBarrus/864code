"""实现第一批只读本地文件工具。"""

import os
from pathlib import Path

from ..model import ToolCall, ToolResult
from .args import optional_path, string_argument
from .output_limits import limit_tool_output
from .path_utils import resolve_workspace_path
from .types import ToolDefinition, ToolHandler


MAX_FILE_READ_BYTES = 1_000_000
IGNORED_SEARCH_DIRECTORIES = {".git", ".epsilon", ".venv", "node_modules"}


def create_read_file_tool(workspace: Path) -> tuple[ToolDefinition, ToolHandler]:
    """创建读取单个文件的工具。"""

    async def read_file(tool_call: ToolCall) -> ToolResult:
        path = resolve_workspace_path(workspace, string_argument(tool_call, "path"))
        if not path.is_file():
            raise ValueError("目标不是文件")
        if path.stat().st_size > MAX_FILE_READ_BYTES:
            raise ValueError("文件超过读取上限（1 MB）")
        return ToolResult(
            call_id=tool_call.call_id,
            content=limit_tool_output(path.read_text(encoding="utf-8")),
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
            capability="file.read",
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
            content=limit_tool_output(content) if content else "目录为空",
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
            capability="file.read",
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
        for directory, directories, filenames in os.walk(root):
            directories[:] = sorted(
                name for name in directories if name not in IGNORED_SEARCH_DIRECTORIES
            )
            for filename in sorted(filenames):
                path = Path(directory, filename)
                if not _is_searchable_file(path):
                    continue
                try:
                    with path.open(encoding="utf-8", errors="replace") as file:
                        for line_number, line in enumerate(file, start=1):
                            if pattern not in line:
                                continue
                            relative_path = path.relative_to(workspace.resolve())
                            match = f"{relative_path}:{line_number}: {line.rstrip()}"
                            content = "\n".join([*matches, match])
                            limited = limit_tool_output(content)
                            if limited != content:
                                return ToolResult(call_id=tool_call.call_id, content=limited)
                            matches.append(match)
                except OSError:
                    continue

        return ToolResult(
            call_id=tool_call.call_id,
            content=limit_tool_output("\n".join(matches)) if matches else "没有找到匹配内容",
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
            capability="file.read",
        ),
        search_files,
    )


def _is_searchable_file(path: Path) -> bool:
    """判断文件是否适合按文本逐行搜索。"""

    try:
        if path.stat().st_size > MAX_FILE_READ_BYTES:
            return False
        with path.open("rb") as file:
            return b"\0" not in file.read(4_096)
    except OSError:
        return False
