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
            raise ValueError("target is not a file")
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return ToolResult(tool_call.call_id, "file content already matches the target")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(tool_call.call_id, "file written")

    return (
        ToolDefinition(
            name="write_file",
            description="Write the given text content to a file",
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
    """创建子串替换工具，保留未匹配到的其余内容。"""

    async def edit_file(tool_call: ToolCall) -> ToolResult:
        path = resolve_workspace_path(workspace, string_argument(tool_call, "path"))
        old_content = string_argument(tool_call, "old_content")
        new_content = text_argument(tool_call, "new_content")
        if not path.is_file():
            raise ValueError("target is not a file")

        current_content = path.read_text(encoding="utf-8")
        if old_content not in current_content:
            if new_content in current_content:
                return ToolResult(tool_call.call_id, "file content already matches the target")
            raise ValueError("file content changed, refusing to overwrite")

        path.write_text(
            current_content.replace(old_content, new_content),
            encoding="utf-8",
        )
        return ToolResult(tool_call.call_id, "file edited")

    return (
        ToolDefinition(
            name="edit_file",
            description="Find a substring in a file and replace it, keeping the rest",
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
