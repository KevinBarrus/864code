"""提供应用层使用的终端工具确认回调。"""

from prompt_toolkit.application import run_in_terminal

from .model import ToolCall
from .tools.types import ToolDefinition


async def confirm_tool_call(
    definition: ToolDefinition,
    tool_call: ToolCall,
) -> bool:
    """暂时离开全屏界面，询问用户是否允许工具执行。"""

    prompt = (
        f"允许执行工具 {definition.name} "
        f"（调用参数：{tool_call.arguments}）？[y/N] "
    )
    answer = await run_in_terminal(
        lambda: input(prompt),
        in_executor=True,
    )
    return answer.strip().lower() in {"y", "yes"}
