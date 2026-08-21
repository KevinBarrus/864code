"""提供 skill 勾选选择组件。"""

import asyncio

from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension

# 来源值到选择器后缀的显示映射
_SOURCE_LABELS = {"project": "projects", "global": "global"}


class SkillPicker:
    """管理 skill 列表、勾选状态和异步结果。"""

    def __init__(
        self,
        items: list[tuple[str, str, str]],
        checked: set[tuple[str, str]],
    ) -> None:
        """创建 skill 选择面板，items 为 (name, description, source) 列表。"""

        self._items = list(items)
        self._checked = set(checked)
        self._cursor = 0
        self._result: asyncio.Future[set[tuple[str, str]] | None] = (
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
        """移动光标，越界时循环到另一端。"""

        if not self._items:
            return
        self._cursor = (self._cursor + offset) % len(self._items)

    def toggle(self) -> None:
        """切换当前项勾选状态。"""

        if not self._items:
            return
        name, _description, source = self._items[self._cursor]
        key = (name, source)
        if key in self._checked:
            self._checked.discard(key)
        else:
            self._checked.add(key)

    def confirm(self) -> None:
        """确认当前勾选集合。"""

        self._resolve(set(self._checked))

    def cancel(self) -> None:
        """取消本次选择。"""

        self._resolve(None)

    async def wait(self) -> set[tuple[str, str]] | None:
        """等待用户完成选择。"""

        return await self._result

    def _resolve(self, result: set[tuple[str, str]] | None) -> None:
        """只允许选择结果被设置一次。"""

        if not self._result.done():
            self._result.set_result(result)

    def _render(self) -> AnyFormattedText:
        """渲染带来源后缀的勾选列表。"""

        fragments: list[tuple[str, str]] = [
            ("", "↑/↓ move, Space toggle, Enter confirm, Esc cancel\n\n")
        ]
        for index, (name, description, source) in enumerate(self._items):
            key = (name, source)
            marker = "√" if key in self._checked else " "
            prefix = "> " if index == self._cursor else "  "
            style = "class:approval-selected" if index == self._cursor else ""
            source_label = _SOURCE_LABELS.get(source, source)
            fragments.append((style, f"{prefix}[{marker}] {name} [{source_label}]"))
            if description:
                fragments.append(("", f"  {description}"))
            fragments.append(("", "\n"))
        return fragments
