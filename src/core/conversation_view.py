"""提供带自动跟随能力的对话滚动容器。"""

from collections.abc import Callable

from prompt_toolkit.layout import ScrollablePane
from prompt_toolkit.layout.containers import Container
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.mouse_events import MouseEvent
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.layout.mouse_handlers import MouseHandlers


class ConversationView(ScrollablePane):
    """在用户查看历史时保持位置，否则自动跟随最新内容。"""

    def __init__(
        self,
        content: Container,
        reserved_height: Callable[[int, int], int] | None = None,
    ) -> None:
        """创建默认跟随底部的滚动容器。"""

        super().__init__(content, show_scrollbar=False)
        self._reserved_height = reserved_height or (lambda _width, _height: 0)
        self._follow_output = True
        self._max_vertical_scroll: int | None = None
        self._viewport_height = 0

    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        """按消息高度自然增长，超出窗口后才成为可伸缩视口。"""

        virtual_width = width - (1 if self.show_scrollbar() else 0)
        content_height = self.content.preferred_height(
            virtual_width,
            self.max_available_height,
        ).preferred
        reserved_height = self._reserved_height(width, max_available_height)

        if content_height + reserved_height < max_available_height:
            # 内容尚未占满窗口，禁止对话区抢占剩余空间。
            return Dimension(min=0, preferred=content_height, max=content_height)

        # 内容已经接近或超过窗口高度，让对话视口吸收剩余空间，
        # 输入框和状态栏自然保持在底部。
        return Dimension(min=0, preferred=0, max=max_available_height, weight=1)

    @property
    def follow_output(self) -> bool:
        """返回当前是否跟随最新输出。"""

        return self._follow_output

    def scroll_to_bottom(self) -> None:
        """恢复跟随最新输出。"""

        self._follow_output = True

    def scroll_by(self, amount: int) -> None:
        """按指定行数滚动，并暂停自动跟随。"""

        self._follow_output = False
        next_scroll = max(0, self.vertical_scroll + amount)
        if self._max_vertical_scroll is not None:
            next_scroll = min(next_scroll, self._max_vertical_scroll)
            # 用户向下滚动到当前内容末尾，表示希望继续跟随模型输出。
            if amount > 0 and next_scroll == self._max_vertical_scroll:
                self._follow_output = True
        self.vertical_scroll = next_scroll

    def scroll_page(self, direction: int) -> None:
        """按当前视口高度翻页，direction 为 1 向下、-1 向上。"""

        page = max(1, self._viewport_height - 1)
        self.scroll_by(direction * page)

    def handle_mouse_event(self, event: MouseEvent) -> None:
        """处理对话区鼠标滚轮，不需要自行计算鼠标坐标。"""

        if event.event_type.name == "SCROLL_UP":
            self.scroll_by(-3)
        elif event.event_type.name == "SCROLL_DOWN":
            self.scroll_by(3)

    def write_to_screen(
        self,
        screen: Screen,
        mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        parent_style: str,
        erase_bg: bool,
        z_index: int | None,
    ) -> None:
        """在跟随模式下根据当前视口高度定位到内容底部。"""

        virtual_width = write_position.width
        content_height = self.content.preferred_height(
            virtual_width,
            self.max_available_height,
        ).preferred
        self._viewport_height = write_position.height
        self._max_vertical_scroll = max(0, content_height - write_position.height)

        if self._follow_output:
            self.vertical_scroll = max(0, content_height - write_position.height)
        else:
            self.vertical_scroll = min(self.vertical_scroll, self._max_vertical_scroll)

        super().write_to_screen(
            screen,
            mouse_handlers,
            write_position,
            parent_style,
            erase_bg,
            z_index,
        )
