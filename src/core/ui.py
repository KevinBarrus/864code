"""实现全屏终端对话界面。"""

import asyncio

from .screen import ChatScreen
from .status import StatusInfo
from .model import Message, ModelClient, ModelClientError


async def run_chat(client: ModelClient, status: StatusInfo) -> None:
    """启动全屏界面，并处理模型的流式回复。"""

    screen: ChatScreen

    async def handle_submit(prompt: str) -> None:
        """发送一轮独立请求，并把结果写入对话区。"""

        screen.add_entry("你", prompt)
        response_index = screen.add_entry("模型", "")

        try:
            async for chunk in client.stream_chat(
                [Message(role="user", content=prompt)]
            ):
                screen.append_to_entry(response_index, chunk)
        except asyncio.CancelledError:
            screen.append_to_entry(response_index, "（已取消）")
            raise
        except ModelClientError as exc:
            screen.append_to_entry(response_index, f"错误：{exc}")

    screen = ChatScreen(status, on_submit=handle_submit)
    await screen.application.run_async()
