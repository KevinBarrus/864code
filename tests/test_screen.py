import asyncio
from pathlib import Path

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.layout.containers import VerticalAlign
from prompt_toolkit.layout.screen import WritePosition
from prompt_toolkit.output import DummyOutput

from core.screen import ChatScreen, DraftState
from core.status import create_status_info
from core.model import ToolCall
from core.tools import ApprovalDecision, ToolDefinition
from core.ui_config import InputLayoutConfig


def _create_screen(tmp_path: Path) -> ChatScreen:
    """创建测试用的全屏界面。"""

    status = create_status_info("test-model", "暂不可查询", tmp_path)
    return ChatScreen(status)


def _approval_definition() -> ToolDefinition:
    """构造测试用写工具定义。"""

    return ToolDefinition(
        name="write_file",
        description="写入文件",
        parameters={"type": "object"},
        source="local",
        permission="write",
        idempotent=True,
    )


def test_chat_screen_uses_full_screen_and_mouse_support(tmp_path: Path) -> None:
    """测试界面启用全屏模式和鼠标支持。"""

    screen = _create_screen(tmp_path)

    assert screen.application.full_screen is True
    assert screen.application.mouse_support() is True


@pytest.mark.asyncio
async def test_approval_replaces_input_and_restores_layout(tmp_path: Path) -> None:
    """测试审批期间只替换输入区并在完成后恢复布局。"""

    with create_app_session(output=DummyOutput()):
        screen = _create_screen(tmp_path)
        task = asyncio.create_task(
            screen.request_approval(
                _approval_definition(),
                ToolCall("call-1", "write_file", {"path": "a.txt"}),
            )
        )
        await asyncio.sleep(0)

        assert screen._approval_prompt is not None
        assert screen._input_container.children == [screen._approval_prompt.window]
        assert screen._layout.container.children[-1].content is screen._status_control

        screen._approval_prompt.confirm()
        result = await task

        assert result.decision == ApprovalDecision.ALLOW_ONCE
        assert screen._approval_prompt is None
        assert screen._input_window in screen._input_container.children


def test_chat_screen_renders_status_with_separate_style_classes(
    tmp_path: Path,
) -> None:
    """测试状态栏分别使用模型、余额和工作目录样式。"""

    screen = _create_screen(tmp_path)

    fragments = screen._render_status()
    styles = [style for style, _ in fragments]
    text = "".join(content for _, content in fragments)

    assert "class:status-model" in styles
    assert "class:status-balance" in styles
    assert "class:status-working-directory" in styles
    assert "test-model" in text
    assert "暂不可查询" in text
    assert str(tmp_path) in text


def test_chat_screen_renders_runtime_status_message(tmp_path: Path) -> None:
    """测试状态栏可以展示运行时降级提示。"""

    screen = _create_screen(tmp_path)
    screen.set_status_message("Session persistence degraded")

    fragments = screen._render_status()
    styles = [style for style, _ in fragments]
    text = "".join(content for _, content in fragments)

    assert "class:status-error" in styles
    assert "Session persistence degraded" in text


def test_chat_screen_appends_conversation_entries(tmp_path: Path) -> None:
    """测试对话区可以追加并渲染模型内容。"""

    screen = _create_screen(tmp_path)
    index = screen.add_entry("assistant", "测试回复")

    assert screen._render_entry(index) == "测试回复"


def test_chat_screen_supports_tool_activity_style(tmp_path: Path) -> None:
    """测试工具活动条目使用独立样式。"""

    screen = _create_screen(tmp_path)
    index = screen.add_entry("tool", "✓ read_file  已读取")

    assert screen._conversation[index].role == "tool"
    assert screen._conversation_content.children[index].style == "class:tool-activity"


def test_chat_screen_uses_scrollable_conversation_view(
    tmp_path: Path,
) -> None:
    """测试对话区使用支持滚动的内容视图。"""

    screen = _create_screen(tmp_path)
    screen.add_entry("assistant", "第一段回复")
    screen.append_to_entry(0, "\n第二段回复")

    assert screen.conversation_view.show_scrollbar() is False
    assert screen._render_entry(0) == "第一段回复\n第二段回复"


def test_streaming_entry_update_does_not_rebuild_conversation_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试连续流式文本只更新目标条目控件。"""

    screen = _create_screen(tmp_path)
    index = screen.add_entry("assistant", "第一段")
    children = screen._conversation_content.children
    control = children[index].content
    sync_calls = 0
    original_sync = screen._sync_conversation_view

    def track_sync() -> None:
        """记录不应发生的全量布局同步。"""

        nonlocal sync_calls
        sync_calls += 1
        original_sync()

    monkeypatch.setattr(screen, "_sync_conversation_view", track_sync)

    screen.append_to_entry(index, "第二段")
    screen.append_to_entry(index, "第三段")

    assert sync_calls == 0
    assert screen._conversation_content.children is children
    assert control.text == "第一段第二段第三段"


def test_adding_history_entries_syncs_conversation_layout_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试恢复历史时只进行一次对话布局同步。"""

    screen = _create_screen(tmp_path)
    sync_calls = 0
    original_sync = screen._sync_conversation_view

    def track_sync() -> None:
        """记录批量恢复触发的布局同步次数。"""

        nonlocal sync_calls
        sync_calls += 1
        original_sync()

    monkeypatch.setattr(screen, "_sync_conversation_view", track_sync)

    screen.add_history_entries(
        [("user", "历史问题"), ("assistant", "历史回答"), ("tool", "工具结果")]
    )

    assert sync_calls == 1
    assert [entry.content for entry in screen._conversation] == [
        "历史问题",
        "历史回答",
        "工具结果",
    ]
    assert screen.conversation_view.follow_output


def test_chat_screen_uses_natural_height_for_conversation_and_input(
    tmp_path: Path,
) -> None:
    """测试对话区和输入区不会强制占满额外空间。"""

    screen = _create_screen(tmp_path)

    assert screen.conversation_view.height is None
    assert screen.input_area.window.dont_extend_height() is True
    assert screen.input_area.window.height.max == 8


def test_chat_screen_does_not_add_an_implicit_fill_area(tmp_path: Path) -> None:
    """测试根布局不会添加撑大输入框或分散状态栏的隐式填充区。"""

    screen = _create_screen(tmp_path)

    assert screen._layout.container.align is VerticalAlign.JUSTIFY


def test_empty_logo_and_conversation_do_not_take_layout_space(
    tmp_path: Path,
) -> None:
    """测试新会话不会因空 Logo 和空对话区产生额外空行。"""

    screen = _create_screen(tmp_path)

    assert screen._has_logo() is False
    assert screen._logo_container.filter() is False
    assert screen._conversation_container.filter() is False


def test_input_container_does_not_expand_vertically(tmp_path: Path) -> None:
    """测试输入容器只占自身高度，不填满剩余屏幕。"""

    screen = _create_screen(tmp_path)

    assert screen._input_window.dont_extend_height() is True


@pytest.mark.asyncio
async def test_layout_keeps_empty_input_small_and_moves_status_to_bottom(
    tmp_path: Path,
) -> None:
    """测试空输入保持自然高度，有对话后剩余空间只交给对话视口。"""

    with create_app_session(output=DummyOutput()):
        screen = _create_screen(tmp_path)
        root = screen._layout.container
        empty_sizes = root._divide_heights(WritePosition(0, 0, 100, 40))

        # 根布局的第 5、7 项分别是输入区和状态栏，中间的 0 是布局间隔。
        assert empty_sizes[4:7] == [3, 0, 1]

        screen.add_entry("user", "用户输入")
        screen.add_entry("assistant", "")
        conversation_sizes = root._divide_heights(WritePosition(0, 0, 100, 40))

        assert conversation_sizes[2] == 3
        assert conversation_sizes[4:7] == [3, 0, 1]


def test_input_vertical_padding_comes_from_config(tmp_path: Path) -> None:
    """测试输入区上下留白使用集中配置。"""

    screen = ChatScreen(
        create_status_info("test-model", "暂不可查询", tmp_path),
        input_layout=InputLayoutConfig(vertical_padding=3),
    )

    assert screen._input_container.children[0].height == 3
    assert screen._input_container.children[2].height == 3


def test_chat_screen_uses_configured_input_spacing(tmp_path: Path) -> None:
    """测试输入区域使用集中配置的内边距和最大行数。"""

    screen = ChatScreen(
        create_status_info("test-model", "暂不可查询", tmp_path),
        input_layout=InputLayoutConfig(
            horizontal_padding=4,
            vertical_padding=2,
            max_lines=6,
        ),
    )

    assert screen.input_area.window.height.max == 6
    assert screen._input_container.children[0].height == 2
    assert screen._input_container.children[2].height == 2


def test_chat_screen_uses_input_box_style_and_blinking_cursor(
    tmp_path: Path,
) -> None:
    """测试输入框使用独立样式并启用闪烁光标。"""

    screen = _create_screen(tmp_path)

    assert (
        screen.application.cursor.get_cursor_shape(screen.application)
        == CursorShape.BLINKING_BEAM
    )
    assert (
        screen.application.style.get_attrs_for_style_str("class:input-area").bgcolor
        == "303030"
    )


def test_user_entry_uses_full_width_gray_style_without_prefix(
    tmp_path: Path,
) -> None:
    """测试用户消息使用整行灰色背景且不显示角色前缀。"""

    screen = _create_screen(tmp_path)
    screen.add_entry("user", "用户输入")

    assert (
        screen.application.style.get_attrs_for_style_str(
            "class:conversation-user"
        ).bgcolor
        == "303030"
    )
    assert screen._render_entry(0) == "用户输入"


def test_input_selection_can_be_copied_and_pasted(tmp_path: Path) -> None:
    """测试输入框支持复制选中文本和粘贴剪贴板内容。"""

    screen = _create_screen(tmp_path)
    screen.input_area.text = "复制内容"
    screen.input_area.buffer.cursor_position = 0
    screen.input_area.buffer.start_selection()
    screen.input_area.buffer.cursor_position = len("复制内容")

    screen.copy_input_selection()
    screen.input_area.buffer.cursor_position = len(screen.input_area.text)
    screen.paste_to_input()

    assert screen.application.clipboard.get_data().text == "复制内容"
    assert screen.input_area.text == "复制内容复制内容"


def test_submitted_input_is_saved_to_in_memory_history(tmp_path: Path) -> None:
    """测试有效提交会写入本次运行的输入历史。"""

    screen = ChatScreen(
        create_status_info("test-model", "暂不可查询", tmp_path),
        on_submit=lambda prompt: None,
    )
    screen.input_area.text = "  第一条输入  "
    key_binding = next(
        binding
        for binding in screen._key_bindings.bindings
        if binding.keys[0].value == "c-m" and binding.filter()
    )

    class FakeApplication:
        """避免测试启动真实后台任务。"""

        def create_background_task(self, coroutine):
            coroutine.close()
            return None

    class FakeEvent:
        """提供提交按键处理器所需的最小应用对象。"""

        app = FakeApplication()

    key_binding.handler(FakeEvent())

    assert isinstance(screen.input_area.buffer.history, InMemoryHistory)
    assert list(screen.input_area.buffer.history.load_history_strings()) == [
        "  第一条输入  "
    ]


def test_chat_screen_accepts_logo_provider(tmp_path: Path) -> None:
    """测试 Logo 接口可以向会话顶部提供内容。"""

    class TestLogo:
        """提供测试 Logo 文本。"""

        def render(self) -> str:
            """返回测试 Logo。"""

            return "864code"

    status = create_status_info("test-model", "暂不可查询", tmp_path)
    screen = ChatScreen(status, logo_provider=TestLogo())

    assert screen._render_logo() == "864code"


@pytest.mark.asyncio
async def test_cancel_request_restores_submitted_draft(tmp_path: Path) -> None:
    """测试取消请求后恢复发送前的输入内容和光标位置。"""

    started = asyncio.Event()
    never_finished = asyncio.Event()

    async def handle_submit(prompt: str) -> None:
        """模拟一个持续等待的模型请求。"""

        started.set()
        await never_finished.wait()

    screen = ChatScreen(
        create_status_info("test-model", "暂不可查询", tmp_path),
        on_submit=handle_submit,
    )
    screen._submitted_draft = DraftState("保留这段文字", 2)
    screen.input_area.text = ""
    task = asyncio.create_task(screen._submit("保留这段文字"))
    screen._request_task = task

    await started.wait()
    screen.cancel_request()
    await task

    assert screen.input_area.text == "保留这段文字"
    assert screen.input_area.buffer.cursor_position == 2
