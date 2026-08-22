"""实现 /clear 命令：清空对话区展示内容。"""

from .registry import CommandContext, SlashCommand


async def clear_command(context: CommandContext) -> None:
    """清空屏幕上的对话展示，会话历史保留在存储中。"""

    context.screen.clear_conversation()


clear_command_slash = SlashCommand(
    name="clear",
    description="Clear the visible conversation",
    handler=clear_command,
)
