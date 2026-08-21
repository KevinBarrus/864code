"""实现本地命令执行工具。"""

import asyncio
import os
import signal
from pathlib import Path

from ..model import ToolCall, ToolResult
from .args import string_argument
from .output_limits import limit_tool_output
from .types import ToolDefinition, ToolHandler

COMMAND_TIMEOUT_SECONDS = 60.0


def create_run_command_tool(
    workspace: Path,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
) -> tuple[ToolDefinition, ToolHandler]:
    """创建以工作区为当前目录的命令执行工具。"""

    if timeout_seconds <= 0:
        raise ValueError("command timeout must be > 0")

    async def run_command(tool_call: ToolCall) -> ToolResult:
        command = string_argument(tool_call, "command")
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workspace.resolve(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            await _stop_process_group(process)
            return ToolResult(
                call_id=tool_call.call_id,
                content=f"command timed out after {timeout_seconds:g}s",
                is_error=True,
                error_category="tool_execution",
            )
        except asyncio.CancelledError:
            await _stop_process_group(process)
            raise

        output = _format_output(stdout, stderr)
        if process.returncode:
            output = f"exit code: {process.returncode}\n{output}"
        output = limit_tool_output(output)
        return ToolResult(
            call_id=tool_call.call_id,
            content=output,
            is_error=process.returncode != 0,
        )

    return (
        ToolDefinition(
            name="run_command",
            description="Execute a shell command in the current workspace",
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
        parts.append(f"stderr:\n{stderr.decode(errors='replace').rstrip()}")
    return "\n".join(parts) or "command executed successfully"


async def _stop_process_group(process: asyncio.subprocess.Process) -> None:
    """终止命令进程组并回收标准输出与错误管道。"""

    if process.returncode is None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1)
        except TimeoutError:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            await process.wait()
    await process.communicate()
