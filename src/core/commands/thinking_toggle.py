"""实现 /thinking-toggle 命令：切换模型思考过程的展示。"""

from .registry import CommandContext, SlashCommand


async def thinking_toggle_command(context: CommandContext) -> None:
    """切换思考过程显示/隐藏，后续流式输出生效。"""

    current = context.agent_loop.show_thinking
    context.agent_loop.set_show_thinking(not current)
    state = "shown" if not current else "hidden"
    context.screen.add_entry("tool", f"Thinking display: {state}")


thinking_toggle_command_slash = SlashCommand(
    name="thinking-toggle",
    description="Toggle display of the model thinking process",
    handler=thinking_toggle_command,
)
