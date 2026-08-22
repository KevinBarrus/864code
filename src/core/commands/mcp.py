"""实现 /mcp 命令：查看当前注册的 MCP 工具。"""

from .registry import CommandContext, SlashCommand


async def mcp_command(context: CommandContext) -> None:
    """列出全部 MCP 来源的工具定义。"""

    if context.tool_manager is None:
        context.screen.add_entry("tool", "MCP tools unavailable")
        return
    tools = [
        definition
        for definition in context.tool_manager.list_definitions()
        if definition.source == "mcp"
    ]
    if not tools:
        context.screen.add_entry("tool", "No MCP tools registered")
        return
    lines = [
        f"mcp tool: {definition.name} - {definition.description}"
        for definition in tools
    ]
    context.screen.add_entry("tool", "\n".join(lines))


mcp_command_slash = SlashCommand(
    name="mcp",
    description="List registered MCP tools",
    handler=mcp_command,
)
