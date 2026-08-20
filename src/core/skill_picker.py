"""提供 skill 勾选选择组件。"""

import asyncio

from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension


class SkillPicker:
    """管理 skill 列表、勾选状态和异步结果。"""

    def __init__(
        self,
        items: list[tuple[str, str]],
        checked: set[str],
    ) -> None:
        """创建 skill 选择面板，items 为 (name, description) 列表。"""

        self._items = list(items)
        self._checked = set(checked)
        self._cursor = 0
        self._result: asyncio.Future[set[str] | None] = (
            asyncio.get_running_loop().create_future()
        )
        self.window = Window(
            content=FormattedTextControl(self._render, focusable=True),
            height=Dimension(min=5, preferred=8),
            dont_extend_height=True,
            wrap_lines=True,
            style="class:approval-area",
        )

    def move(self, offset: int) -> None:
        """移动光标，限制在列表范围内。"""

        if not self._items:
            return
        self._cursor = max(0, min(len(self._items) - 1, self._cursor + offset))

    def toggle(self) -> None:
        """切换当前项勾选状态。"""

        if not self._items:
            return
        name = self._items[self._cursor][0]
        if name in self._checked:
            self._checked.discard(name)
        else:
            self._checked.add(name)

    def confirm(self) -> None:
        """确认当前勾选集合。"""

        self._resolve(set(self._checked))

    def cancel(self) -> None:
        """取消本次选择。"""

        self._resolve(None)

    async def wait(self) -> set[str] | None:
        """等待用户完成选择。"""

        return await self._result

    def _resolve(self, result: set[str] | None) -> None:
        """只允许选择结果被设置一次。"""

        if not self._result.done():
            self._result.set_result(result)

    def _render(self) -> AnyFormattedText:
        """渲染勾选列表。"""

        fragments: list[tuple[str, str]] = [
            ("", "↑/↓ 移动，Space 勾选，Enter 确认，Esc 取消\n\n")
        ]
        for index, (name, description) in enumerate(self._items):
            marker = "√" if name in self._checked else " "
            prefix = "> " if index == self._cursor else "  "
            style = "class:approval-selected" if index == self._cursor else ""
            fragments.append((style, f"{prefix}[{marker}] {name}"))
            if description:
                fragments.append(("", f"  {description}"))
            fragments.append(("", "\n"))
        return fragments
