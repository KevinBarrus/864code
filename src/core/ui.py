"""实现全屏终端对话界面。"""

import asyncio

from .screen import ChatScreen
from .status import StatusInfo
from .model import ModelClient, ModelClientError
from .memory import Memory


async def run_chat(client: ModelClient, status: StatusInfo) -> None:
    """启动全屏界面，并处理模型的流式回复。"""

    screen: ChatScreen
    memory = Memory()

    async def handle_submit(prompt: str) -> None:
        """发送请求，并同步当前会话的消息历史。"""

        # 先更新界面，让用户立即看到本轮输入和待生成的回复区域
        screen.add_entry("你", prompt)
        response_index = screen.add_entry("模型", "")
        response_parts: list[str] = []

        # 用户消息必须先进入记忆，模型才能在本轮请求中看到它
        memory.add_user_message(prompt)

        try:
            # 使用完整会话历史请求模型，并把流式片段同时保存和展示
            async for chunk in client.stream_chat(memory.get_messages()):
                response_parts.append(chunk)
                screen.append_to_entry(response_index, chunk)
        except asyncio.CancelledError:
            # 取消时保留已生成的部分回复，供下一轮继续参考
            response = "".join(response_parts)
            if response:
                memory.add_assistant_message(response)
            screen.append_to_entry(response_index, "（已取消）")
            raise
        except ModelClientError as exc:
            # 模型请求失败只展示错误，不把错误提示写入模型记忆
            screen.append_to_entry(response_index, f"错误：{exc}")
        else:
            # 流式响应完成后，再一次性保存完整的模型消息
            response = "".join(response_parts)
            if response:
                memory.add_assistant_message(response)

    screen = ChatScreen(status, on_submit=handle_submit)
    await screen.application.run_async()
