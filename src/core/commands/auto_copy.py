"""实现 /auto-copy 命令：切换输入框拖选自动复制开关。"""

from .registry import CommandContext, SlashCommand


async def auto_copy_command(context: CommandContext) -> None:
    """切换输入框选中松开自动复制，状态不写入状态栏。"""

    current = context.screen._auto_copy
    context.screen.set_auto_copy(not current)
    state = "on" if not current else "off"
    context.screen.add_entry("tool", f"Auto-copy: {state}")


auto_copy_command_slash = SlashCommand(
    name="auto-copy",
    description="Toggle auto-copy of input selections",
    handler=auto_copy_command,
)
