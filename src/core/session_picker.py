"""提供会话恢复时的键盘选择界面。"""

from collections.abc import Iterable

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from .session_store import SessionSummary


class SessionPicker:
    """展示会话摘要并返回用户选中的 Session ID。"""

    def __init__(self, summaries: Iterable[SessionSummary]) -> None:
        """创建会话选择器并默认选中第一项。"""

        self._summaries = list(summaries)
        self._selected_index = 0

    async def pick(self) -> str | None:
        """启动选择界面并返回选中的 Session ID。"""

        if not self._summaries:
            return None

        application = Application(
            layout=Layout(
                Window(
                    content=FormattedTextControl(self._render),
                    wrap_lines=False,
                )
            ),
            key_bindings=self._create_key_bindings(),
            style=Style.from_dict({"selected": "fg:ansiblue"}),
            full_screen=True,
        )
        return await application.run_async()

    def move_selection(self, offset: int) -> None:
        """按照偏移量移动当前选中项并限制在列表范围内。"""

        if not self._summaries:
            return
        self._selected_index = min(
            max(self._selected_index + offset, 0),
            len(self._summaries) - 1,
        )

    def _create_key_bindings(self) -> KeyBindings:
        """创建上下移动、确认和取消的快捷键。"""

        key_bindings = KeyBindings()

        @key_bindings.add("up")
        def move_up(event) -> None:
            """选择上一条会话"""

            self.move_selection(-1)
            event.app.invalidate()

        @key_bindings.add("down")
        def move_down(event) -> None:
            """选择下一条会话"""

            self.move_selection(1)
            event.app.invalidate()

        @key_bindings.add("enter")
        def confirm(event) -> None:
            """确认当前会话"""

            event.app.exit(result=self._summaries[self._selected_index].session_id)

        @key_bindings.add("escape")
        def cancel(event) -> None:
            """取消会话恢复"""

            event.app.exit(result=None)

        return key_bindings

    def _render(self) -> AnyFormattedText:
        """渲染提示语和会话列表"""

        if not self._summaries:
            return "没有可恢复的会话\n按 Esc 退出"

        rendered: list[tuple[str, str]] = [
            ("", "↑/↓ 选择，Enter 进入，Esc 退出\n\n")
        ]
        for index, summary in enumerate(self._summaries):
            prefix = "> " if index == self._selected_index else "  "
            style = "class:selected" if index == self._selected_index else ""
            updated_at = summary.updated_at.astimezone().strftime(
                "%Y-%m-%d %H:%M"
            )
            rendered.extend(
                [
                    (style, f"{prefix}{summary.title}"),
                    ("", f"    {updated_at}    {summary.session_id[:8]}\n"),
                ]
            )
        return rendered
