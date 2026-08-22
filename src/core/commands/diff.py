"""实现 /diff 命令：显示当前 git diff。"""

import asyncio

from .registry import CommandContext, SlashCommand

_MAX_DIFF_CHARS = 4000


async def diff_command(context: CommandContext) -> None:
    """运行 git diff 并截断显示结果。"""

    process = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        cwd=context.project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    output = stdout.decode(errors="replace")
    error_text = stderr.decode(errors="replace").strip()
    if process.returncode != 0:
        context.screen.add_entry("tool", f"git diff failed: {error_text[:200]}")
        return
    if not output.strip():
        context.screen.add_entry("tool", "No changes to show")
        return
    if len(output) > _MAX_DIFF_CHARS:
        output = output[:_MAX_DIFF_CHARS] + "\n… (truncated)"
    context.screen.add_entry("tool", output)


diff_command_slash = SlashCommand(
    name="diff",
    description="Show the current git diff",
    handler=diff_command,
)
