"""提供嵌入输入区域的单行文本输入组件。"""

import asyncio

from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.layout import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import TextArea


class InputPrompt:
    """单行文本输入框，Enter 确认、Esc 取消，密码模式隐藏输入内容。"""

    def __init__(self, title: str, is_password: bool = False) -> None:
        """创建输入面板，title 为提示语。"""

        self._title = title
        self._result: asyncio.Future[str | None] = (
            asyncio.get_running_loop().create_future()
        )
        self._input = TextArea(
            multiline=False,
            password=is_password,
            height=Dimension(min=1, max=1),
            dont_extend_height=True,
            style="class:approval-area",
        )
        self.window = HSplit(
            [
                Window(
                    FormattedTextControl(self._render_title),
                    height=Dimension(min=1, max=1),
                    wrap_lines=True,
                    dont_extend_height=True,
                ),
                self._input,
            ],
            style="class:approval-area",
        )

    @property
    def input_area(self) -> TextArea:
        """返回内部输入框，供界面聚焦。"""

        return self._input

    def confirm(self) -> None:
        """确认当前输入内容，空内容视为取消。"""

        value = self._input.text.strip()
        self._resolve(value or None)

    def cancel(self) -> None:
        """取消本次输入。"""

        self._resolve(None)

    async def wait(self) -> str | None:
        """等待用户完成输入。"""

        return await self._result

    def _resolve(self, result: str | None) -> None:
        """只允许输入结果被设置一次。"""

        if not self._result.done():
            self._result.set_result(result)

    def _render_title(self) -> AnyFormattedText:
        """渲染提示语文本。"""

        return [("", f"{self._title}\n")]
