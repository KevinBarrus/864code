"""提供会话恢复时的选择界面（Codex 风格：多行记录、相对时间、交替行、过滤）。"""

from collections.abc import Iterable
from datetime import datetime, timezone

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
from wcwidth import wcswidth

from .session_store import SessionSummary

_TITLE_WIDTH = 48
_META_GAP = 3


def format_relative_time(updated_at: datetime, now: datetime) -> str:
    """把会话更新时间格式化为简洁的相对时间。"""

    seconds = max(0, int((now - updated_at).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


class SessionPicker:
    """展示会话摘要并返回用户选中的 Session ID，支持输入过滤。"""

    def __init__(self, summaries: Iterable[SessionSummary]) -> None:
        """创建会话选择器并默认选中第一项。"""

        self._all_summaries = list(summaries)
        self._filter_text = ""
        self._selected_index = 0
        self._application: Application | None = None
        self._filter_area = TextArea(
            prompt="filter: ",
            multiline=False,
            height=Dimension(min=1, max=1),
            wrap_lines=False,
        )
        self._filter_area.buffer.on_text_changed += self._on_filter_changed

    @property
    def _summaries(self) -> list[SessionSummary]:
        """返回过滤后的会话列表。"""

        keyword = self._filter_text.strip().lower()
        if not keyword:
            return self._all_summaries
        return [
            summary
            for summary in self._all_summaries
            if keyword in summary.title.lower()
            or keyword in summary.session_id.lower()
        ]

    def _on_filter_changed(self, buffer) -> None:
        """过滤文本变化时重置选中并刷新列表。"""

        self._filter_text = buffer.text
        self._selected_index = 0
        if self._application is not None:
            self._application.invalidate()

    async def pick(self) -> str | None:
        """启动选择界面并返回选中的 Session ID。"""

        if not self._all_summaries:
            return None

        self._application = Application(
            layout=Layout(
                HSplit(
                    [
                        self._filter_area,
                        Window(
                            content=FormattedTextControl(self._render),
                            wrap_lines=False,
                        ),
                    ]
                )
            ),
            key_bindings=self._create_key_bindings(),
            style=Style.from_dict(
                {
                    "selected": "fg:ansibrightcyan",
                    "zebra": "bg:#262626",
                    "meta": "fg:#808080",
                }
            ),
            full_screen=True,
            focused_element=self._filter_area,
        )
        return await self._application.run_async()

    def move_selection(self, offset: int) -> None:
        """按照偏移量移动当前选中项并限制在列表范围内。"""

        summaries = self._summaries
        if not summaries:
            return
        self._selected_index = min(
            max(self._selected_index + offset, 0),
            len(summaries) - 1,
        )

    def _create_key_bindings(self) -> KeyBindings:
        """创建上下移动、确认和取消的快捷键（eager 覆盖过滤框内部绑定）。"""

        key_bindings = KeyBindings()

        @key_bindings.add("up", eager=True)
        def move_up(event) -> None:
            """选择上一条会话"""

            self.move_selection(-1)
            event.app.invalidate()

        @key_bindings.add("down", eager=True)
        def move_down(event) -> None:
            """选择下一条会话"""

            self.move_selection(1)
            event.app.invalidate()

        @key_bindings.add("enter", eager=True)
        def confirm(event) -> None:
            """确认当前会话"""

            summaries = self._summaries
            if summaries:
                event.app.exit(result=summaries[self._selected_index].session_id)

        @key_bindings.add("escape", eager=True)
        def cancel(event) -> None:
            """取消会话恢复"""

            event.app.exit(result=None)

        return key_bindings

    def _render(self) -> AnyFormattedText:
        """渲染过滤输入与多行会话列表（标题 + 相对时间，选中高亮、交替底色）。"""

        fragments: list[tuple[str, str]] = []
        now = datetime.now(timezone.utc)
        title_width = max(
            (wcswidth(summary.title) for summary in self._summaries),
            default=_TITLE_WIDTH,
        )
        title_width = min(title_width, _TITLE_WIDTH)
        for index, summary in enumerate(self._summaries):
            title = _truncate(summary.title, title_width)
            meta = (
                format_relative_time(summary.updated_at, now)
                + "  "
                + summary.session_id[:8]
            )
            if index == self._selected_index:
                fragments.append(("class:selected", f"› {title}  {meta}\n"))
            else:
                zebra = "class:zebra" if index % 2 == 1 else ""
                fragments.append((zebra, f"  {title}"))
                fragments.append((zebra, " " * _META_GAP + meta + "\n"))
        if not self._summaries:
            fragments.append(("", "No matching sessions\n"))
        return fragments


def _truncate(text: str, width: int) -> str:
    """按显示宽度截断文本并追加省略号。"""

    if wcswidth(text) <= width:
        return text
    return text[: width - 1] + "…"
