"""OSC52 剪贴板与选区复制的单元测试。"""

import base64

from prompt_toolkit.application import create_app_session
from prompt_toolkit.clipboard import ClipboardData
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

from core.clipboard import Osc52Clipboard, copy_text_to_clipboard
from core.screen import SelectionPane


def test_osc52_clipboard_keeps_memory_and_encodes_base64(
    monkeypatch,
) -> None:
    """测试写入系统剪贴板时保存内存副本并编码为 OSC52 负载。"""

    written: list[str] = []
    monkeypatch.setattr("core.clipboard._write_osc52", written.append)

    clipboard = Osc52Clipboard()
    clipboard.set_text("你好")

    assert clipboard.get_data().text == "你好"
    assert written == [
        base64.b64encode("你好".encode("utf-8")).decode("ascii")
    ]


def test_copy_text_to_clipboard_encodes_base64(monkeypatch) -> None:
    """测试对话区复制入口同样使用 OSC52 编码。"""

    written: list[str] = []
    monkeypatch.setattr("core.clipboard._write_osc52", written.append)

    copy_text_to_clipboard("abc")

    assert written == [base64.b64encode(b"abc").decode("ascii")]


class _FakeContent:
    """渲染一行固定文本的占位容器。"""

    def __init__(self, text: str) -> None:
        self._window = Window(content=FormattedTextControl(text))

    def preferred_width(self, max_available_width: int) -> Dimension:
        return self._window.preferred_width(max_available_width)

    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        return self._window.preferred_height(width, max_available_height)

    def reset(self) -> None:
        self._window.reset()

    def get_children(self):
        return []

    def is_focusable(self) -> bool:
        return False

    def write_to_screen(self, screen, mouse_handlers, write_position, parent_style, erase_bg, z_index):
        self._window.write_to_screen(
            screen,
            mouse_handlers,
            write_position,
            parent_style,
            erase_bg,
            z_index,
        )


def _render(selection_pane: SelectionPane) -> Screen:
    """把选区容器渲染到一块 20x4 的测试屏幕。"""

    screen = Screen()
    mouse_handlers = MouseHandlers()
    selection_pane.write_to_screen(
        screen,
        mouse_handlers,
        WritePosition(0, 0, 20, 4),
        "",
        False,
        None,
    )
    return screen


def _mouse(selection_pane: SelectionPane, event_type, x: int, y: int) -> None:
    """向选区容器发送一个左键鼠标事件。"""

    from prompt_toolkit.layout.screen import Point

    selection_pane._mouse_handler(
        MouseEvent(
            position=Point(x=x, y=y),
            event_type=event_type,
            button=MouseButton.LEFT,
            modifiers=MouseEventType.MOUSE_UP,  # 仅占位
        )
    )


def test_selection_pane_extracts_and_copies_text() -> None:
    """测试拖选松开后把选区文本交给复制回调。"""

    copied: list[str] = []
    pane = SelectionPane(_FakeContent("hello world"), scroll_handler=lambda _: None, on_copy=copied.append)

    _render(pane)
    _mouse(pane, MouseEventType.MOUSE_DOWN, 0, 0)
    _mouse(pane, MouseEventType.MOUSE_UP, 4, 0)

    assert copied == ["hello"]


def test_selection_pane_highlights_selected_region() -> None:
    """测试选区内的字符叠加反色样式。"""

    pane = SelectionPane(_FakeContent("hello world"), scroll_handler=lambda _: None)

    screen = _render(pane)
    _mouse(pane, MouseEventType.MOUSE_DOWN, 0, 0)
    _mouse(pane, MouseEventType.MOUSE_MOVE, 2, 0)

    screen = _render(pane)

    assert "reverse" in screen.data_buffer[0][0].style
    assert "reverse" in screen.data_buffer[0][2].style
    assert "reverse" not in screen.data_buffer[0][4].style
