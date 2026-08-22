"""提供命令补全单选列表组件。"""

from collections.abc import Callable

from prompt_toolkit.completion import Completion
from prompt_toolkit.formatted_text import AnyFormattedText, to_plain_text
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from wcwidth import wcswidth

# name 与 description 之间的最小间距（对齐 Pi PRIMARY_COLUMN_GAP）
_DESCRIPTION_GAP = 3


class CommandPicker:
    """渲染补全匹配项，管理选中与滚动。"""

    # 窗口优先高度下可同时展示的行数，用于滚动跟随
    _VISIBLE_ROWS = 6

    def __init__(
        self,
        completions: list[Completion],
        on_apply: Callable[[Completion], None] | None = None,
    ) -> None:
        """保存补全项并默认选中第一项，点击行时应用该补全。"""

        self._completions = list(completions)
        self._on_apply = on_apply
        self._cursor = 0
        self.window = Window(
            content=FormattedTextControl(self._render, focusable=True),
            height=Dimension(min=1, preferred=self._VISIBLE_ROWS),
            dont_extend_height=True,
            wrap_lines=True,
        )
        self.window.vertical_scroll = 0

    def move(self, offset: int) -> None:
        """移动光标，越界时循环到另一端并保持选中项可见。"""

        if not self._completions:
            return
        self._cursor = (self._cursor + offset) % len(self._completions)
        self._follow_cursor()

    @property
    def selected(self) -> Completion | None:
        """返回当前选中的补全项。"""

        if not self._completions:
            return None
        return self._completions[self._cursor]

    def _follow_cursor(self) -> None:
        """滚动窗口让当前光标项始终可见。"""

        max_scroll = max(0, len(self._completions) - self._VISIBLE_ROWS)
        desired_scroll = max(0, self._cursor - (self._VISIBLE_ROWS - 1))
        self.window.vertical_scroll = min(max_scroll, desired_scroll)

    def _click(self, index: int) -> None:
        """鼠标点击某行：选中该项并应用补全。"""

        self._cursor = index
        self._follow_cursor()
        if self._on_apply is not None and self._completions:
            self._on_apply(self._completions[index])

    def _render(self) -> AnyFormattedText:
        """渲染命令名与描述：name 列按最大宽度对齐，支持鼠标点击应用。"""

        names = [f"/{completion.text}" for completion in self._completions]
        metas = [
            to_plain_text(completion.display_meta)
            if completion.display_meta
            else ""
            for completion in self._completions
        ]
        name_width = max((wcswidth(name) for name in names), default=0)
        fragments: list[tuple[str, str, Callable]] = []
        for index, completion in enumerate(self._completions):
            prefix = "› " if index == self._cursor else "  "
            spacing = " " * max(1, name_width - wcswidth(names[index]) + _DESCRIPTION_GAP)
            handler = lambda event, i=index: self._click(i)
            if index == self._cursor:
                # 选中项整行亮青（对齐 Pi selectedText）
                fragments.append(
                    ("class:approval-selected", f"{prefix}{names[index]}{spacing}{metas[index]}", handler)
                )
            else:
                fragments.append(("", f"{prefix}{names[index]}", handler))
                if metas[index]:
                    fragments.append(
                        ("class:completion-description", f"{spacing}{metas[index]}", handler)
                    )
            fragments.append(("", "\n", handler))
        return fragments
