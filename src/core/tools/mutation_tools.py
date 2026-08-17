"""实现本地文件写入和编辑工具。"""

from pathlib import Path

from ..model import ToolCall, ToolResult
from .args import string_argument, text_argument
from .path_utils import resolve_workspace_path
from .types import ToolDefinition, ToolHandler


def create_write_file_tool(workspace: Path) -> tuple[ToolDefinition, ToolHandler]:
    """创建写入文件最终内容的工具。"""

    async def write_file(tool_call: ToolCall) -> ToolResult:
        path = resolve_workspace_path(workspace, string_argument(tool_call, "path"))
        content = text_argument(tool_call, "content")
        if path.exists() and not path.is_file():
            raise ValueError("目标不是文件")
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return ToolResult(tool_call.call_id, "文件内容已经是目标内容")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(tool_call.call_id, "文件已写入")

    return (
        ToolDefinition(
            name="write_file",
            description="将文件写入指定的最终文本内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            source="local",
            permission="write",
            idempotent=True,
            capability="file.write",
        ),
        write_file,
    )


def create_edit_file_tool(workspace: Path) -> tuple[ToolDefinition, ToolHandler]:
    """创建带旧内容校验的完整文件替换工具。"""

    async def edit_file(tool_call: ToolCall) -> ToolResult:
        path = resolve_workspace_path(workspace, string_argument(tool_call, "path"))
        old_content = text_argument(tool_call, "old_content")
        new_content = text_argument(tool_call, "new_content")
        if not path.is_file():
            raise ValueError("目标不是文件")

        current_content = path.read_text(encoding="utf-8")
        if current_content == new_content:
            return ToolResult(tool_call.call_id, "文件内容已经是目标内容")
        if current_content != old_content:
            raise ValueError("文件内容已变化，拒绝覆盖")

        path.write_text(new_content, encoding="utf-8")
        return ToolResult(tool_call.call_id, "文件已编辑")

    return (
        ToolDefinition(
            name="edit_file",
            description="在旧内容匹配时将文件替换为新的完整内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_content": {"type": "string"},
                    "new_content": {"type": "string"},
                },
                "required": ["path", "old_content", "new_content"],
            },
            source="local",
            permission="write",
            idempotent=True,
            capability="file.write",
        ),
        edit_file,
    )
