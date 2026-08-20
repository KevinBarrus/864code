"""slash command 注册表与内置命令。"""

from .registry import (
    CommandContext,
    CommandRegistrationError,
    CommandRegistry,
    SlashCommand,
)
from .start_skill import start_skill_command
from .stop_skill import stop_skill_command

__all__ = [
    "CommandContext",
    "CommandRegistrationError",
    "CommandRegistry",
    "SlashCommand",
    "start_skill_command",
    "stop_skill_command",
]
