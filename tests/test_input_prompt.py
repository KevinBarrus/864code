"""测试单行文本输入组件。"""

import pytest
from prompt_toolkit.filters.base import Always
from prompt_toolkit.layout.processors import PasswordProcessor

from core.input_prompt import InputPrompt


def _password_processor_active(prompt: InputPrompt) -> bool:
    """检查 TextArea 是否启用了密码遮罩处理器。"""

    return any(
        isinstance(getattr(processor, "processor", None), PasswordProcessor)
        and isinstance(getattr(processor, "filter", None), Always)
        for processor in prompt._input.control.input_processors
    )


@pytest.mark.asyncio
async def test_input_prompt_confirm_returns_text() -> None:
    """测试确认返回去除首尾空白的输入内容。"""

    prompt = InputPrompt("输入 API key")

    prompt._input.text = "  secret-key  "
    prompt.confirm()

    assert await prompt.wait() == "secret-key"


@pytest.mark.asyncio
async def test_input_prompt_empty_confirm_returns_none() -> None:
    """测试空输入确认视为取消。"""

    prompt = InputPrompt("输入")

    prompt.confirm()

    assert await prompt.wait() is None


@pytest.mark.asyncio
async def test_input_prompt_cancel_returns_none() -> None:
    """测试取消返回 None。"""

    prompt = InputPrompt("输入")

    prompt._input.text = "abc"
    prompt.cancel()

    assert await prompt.wait() is None


@pytest.mark.asyncio
async def test_input_prompt_password_hides_text() -> None:
    """测试密码模式开启时会启用输入遮罩。"""

    prompt = InputPrompt("API key", is_password=True)

    assert _password_processor_active(prompt) is True
