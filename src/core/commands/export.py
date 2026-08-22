"""实现 /export 命令：将会话导出为 Markdown 文件。"""

from datetime import datetime

from .registry import CommandContext, SlashCommand

_ROLE_LABELS = {"user": "User", "assistant": "Assistant", "tool": "Tool"}


async def export_command(context: CommandContext) -> None:
    """把会话消息按角色写入带时间戳的 Markdown 文件。"""

    messages = context.session.get_messages()
    if not messages:
        context.screen.add_entry("tool", "No messages to export")
        return
    blocks = []
    for message in messages:
        role = _ROLE_LABELS.get(message.role, message.role)
        blocks.append(f"## {role}\n\n{message.content}")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = context.project_dir / f"conversation-{timestamp}.md"
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    context.screen.add_entry("tool", f"Exported {len(messages)} messages to {path}")


export_command_slash = SlashCommand(
    name="export",
    description="Export the conversation as Markdown",
    handler=export_command,
)
