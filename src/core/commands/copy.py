"""实现 /copy 命令：复制最后一条助手回复到系统剪贴板。"""

import asyncio

from ..clipboard import copy_text_to_clipboard
from .registry import CommandContext, SlashCommand


async def copy_command(context: CommandContext) -> None:
    """把会话中最后一条助手回复写入剪贴板。"""

    messages = context.session.get_messages()
    last_assistant = next(
        (message for message in reversed(messages) if message.role == "assistant"),
        None,
    )
    if last_assistant is None:
        context.screen.add_entry("tool", "No assistant response to copy")
        return
    await asyncio.to_thread(copy_text_to_clipboard, last_assistant.content)
    context.screen.add_entry(
        "tool", f"Copied {len(last_assistant.content)} chars to clipboard"
    )


copy_command_slash = SlashCommand(
    name="copy",
    description="Copy the last assistant response to clipboard",
    handler=copy_command,
)
