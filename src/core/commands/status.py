"""实现 /status 命令：显示会话、模型与上下文状态。"""

from .registry import CommandContext, SlashCommand


async def status_command(context: CommandContext) -> None:
    """展示当前会话的模型、工作区、上下文用量与推理档位。"""

    settings = context.client_holder.settings
    messages = context.session.get_messages()
    estimated = context.context_manager.estimate_tokens(messages)
    lines = [
        f"model: {settings.model_name}",
        f"base url: {settings.base_url}",
        f"workspace: {context.project_dir}",
        f"thinking level: {context.agent_loop.thinking_level}",
        f"messages: {len(messages)}",
        f"context window: {context.context_manager.context_window()} tokens",
        f"estimated usage: {estimated} tokens",
    ]
    context.screen.add_entry("tool", "\n".join(lines))


status_command_slash = SlashCommand(
    name="status",
    description="Show session configuration and token usage",
    handler=status_command,
)
