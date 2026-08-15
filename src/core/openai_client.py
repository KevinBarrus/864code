"""OpenAI-compatible 模型客户端实现。"""

import asyncio
from collections.abc import AsyncIterator, Sequence

from openai import AsyncOpenAI

from .config import Settings
from .model import Message, ModelClientError


class OpenAICompatibleClient:
    """使用 OpenAI SDK 调用 OpenAI-compatible 服务。"""

    def __init__(
        self,
        settings: Settings,
        client: AsyncOpenAI | None = None,
    ) -> None:
        """根据配置创建客户端，也允许注入测试客户端。"""

        self._model_name = settings.model_name
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
        )

    async def stream_chat(
        self,
        messages: Sequence[Message],
    ) -> AsyncIterator[str]:
        """发送消息并逐段返回模型生成的文本。"""

        request_messages = [
            {"role": message.role, "content": message.content}
            for message in messages
        ]

        try:
            stream = await self._client.chat.completions.create(
                model=self._model_name,
                messages=request_messages,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ModelClientError("模型请求失败，请检查配置和网络连接") from exc
