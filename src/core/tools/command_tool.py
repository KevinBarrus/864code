"""实现本地命令执行工具。"""

import asyncio
from pathlib import Path

from ..model import ToolCall, ToolResult
from .args import string_argument
from .types import ToolDefinition, ToolHandler


def create_run_command_tool(workspace: Path) -> tuple[ToolDefinition, ToolHandler]:
    """创建以工作区为当前目录的命令执行工具。"""

    async def run_command(tool_call: ToolCall) -> ToolResult:
        command = string_argument(tool_call, "command")
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workspace.resolve(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            raise

        output = _format_output(stdout, stderr)
        if process.returncode:
            output = f"退出码：{process.returncode}\n{output}"
        return ToolResult(
            call_id=tool_call.call_id,
            content=output,
            is_error=process.returncode != 0,
        )

    return (
        ToolDefinition(
            name="run_command",
            description="在当前工作区中执行 shell 命令",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            source="local",
            permission="command",
            idempotent=False,
        ),
        run_command,
    )


def _format_output(stdout: bytes, stderr: bytes) -> str:
    """合并命令的标准输出和错误输出。"""

    parts: list[str] = []
    if stdout:
        parts.append(stdout.decode(errors="replace").rstrip())
    if stderr:
        parts.append(f"错误输出：\n{stderr.decode(errors='replace').rstrip()}")
    return "\n".join(parts) or "命令执行成功"
