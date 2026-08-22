"""实现 /thinking 命令：选择推理强度档位。"""

from .registry import CommandContext, SlashCommand

THINKING_LEVELS = ("off", "low", "medium", "high", "xhigh")
DEFAULT_THINKING_LEVEL = "high"
_CHOICE_HINTS = "↑/↓ move, Enter confirm, Esc cancel"


async def thinking_command(context: CommandContext) -> None:
    """弹出推理强度选择器并应用选中的档位。"""

    current = context.agent_loop.thinking_level
    choice = await context.screen.request_choice_picker(
        list(THINKING_LEVELS),
        f"Select thinking level (current: {current}, {_CHOICE_HINTS})",
    )
    if choice is None or choice == current:
        return
    context.agent_loop.set_thinking_level(choice)
    context.screen.add_entry("tool", f"Switched thinking level: {choice}")


thinking_command_slash = SlashCommand(
    name="thinking",
    description="Select thinking level (reasoning effort)",
    handler=thinking_command,
)
