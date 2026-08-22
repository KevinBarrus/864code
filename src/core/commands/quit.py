"""实现 /quit 命令：退出全屏界面。"""

from .registry import CommandContext, SlashCommand


async def quit_command(context: CommandContext) -> None:
    """结束当前会话并退出界面。"""

    context.screen.application.exit()


quit_command_slash = SlashCommand(
    name="quit",
    description="Exit the application",
    handler=quit_command,
)
