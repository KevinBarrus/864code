import asyncio
from pathlib import Path

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.completion import Completion
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.formatted_text import to_plain_text
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.layout.containers import VerticalAlign
from prompt_toolkit.layout.screen import WritePosition
from prompt_toolkit.output import DummyOutput

from core.screen import ChatScreen, DraftState, SlashCommandCompleter
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


def _binding_key(binding) -> str:
    """返回绑定的第一个键值，兼容字符串键和枚举键。"""

    key = binding.keys[0]
    return key.value if hasattr(key, "value") else key


def test_chat_screen_uses_full_screen_and_mouse_support(tmp_path: Path) -> None:
    """测试界面启用全屏模式和鼠标支持。"""

    screen = _create_screen(tmp_path)

    assert screen.application.full_screen is True
    assert screen.application.mouse_support() is True


@pytest.mark.asyncio
async def test_approval_replaces_bottom_area_and_restores_layout(tmp_path: Path) -> None:
    """测试审批期间显示在输入区下方并在完成后恢复状态栏。"""

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
        assert screen._bottom_container.children == [screen._approval_prompt.window]
        assert screen._layout.container.children[-1].children[0] is screen._approval_prompt.window

        screen._approval_prompt.confirm()
        result = await task

        assert result.decision == ApprovalDecision.ALLOW_ONCE
        assert screen._approval_prompt is None
        assert screen._bottom_container.children == [screen._status_window]


@pytest.mark.asyncio
async def test_skill_picker_replaces_bottom_area_and_restores_layout(tmp_path: Path) -> None:
    """测试 skill 选择期间显示在输入区下方并在完成后恢复状态栏。"""

    with create_app_session(output=DummyOutput()):
        screen = _create_screen(tmp_path)
        task = asyncio.create_task(
            screen.request_skill_picker([("a", "A 描述", "project")], checked=set())
        )
        await asyncio.sleep(0)

        assert screen._skill_picker is not None
        assert screen._bottom_container.children == [screen._skill_picker.window]

        screen._skill_picker.toggle()   # 勾选 ("a", "project")
        screen._skill_picker.confirm()
        result = await task

        assert result == {("a", "project")}
        assert screen._skill_picker is None
        assert screen._bottom_container.children == [screen._status_window]


def test_chat_screen_renders_status_rows(tmp_path: Path) -> None:
    """测试两行式状态栏：行一左工作区、行二左信息、右模型名。"""

    screen = _create_screen(tmp_path)

    row1_left, row1_right = screen._status_rows()[0]
    row2_left, row2_right = screen._status_rows()[1]

    assert "test-model" in row2_right
    assert "暂不可查询" in row2_left
    assert str(tmp_path) in row1_left
    assert row1_right == ""


def test_chat_screen_renders_runtime_status_message(tmp_path: Path) -> None:
    """测试状态栏行一可以展示运行时降级提示。"""

    screen = _create_screen(tmp_path)
    screen.set_status_message("Session persistence degraded")

    left, _ = screen._status_rows()[0]

    assert "Session persistence degraded" in left


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


def test_tool_entry_style_can_be_updated(tmp_path: Path) -> None:
    """测试工具条目样式可从待执行更新为成功/错误。"""

    screen = _create_screen(tmp_path)
    index = screen.add_entry(
        "tool", "▸ read_file  ...", style="class:tool-pending"
    )

    assert screen._conversation_content.children[index].style == "class:tool-pending"

    screen.set_entry_style(index, "class:tool-success")

    assert screen._conversation_content.children[index].style == "class:tool-success"
    assert screen._conversation[index].style == "class:tool-success"


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
    assert to_plain_text(control.text) == "第一段第二段第三段"


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
        assert empty_sizes[4:7] == [3, 0, 2]

        screen.add_entry("user", "用户输入")
        screen.add_entry("assistant", "")
        conversation_sizes = root._divide_heights(WritePosition(0, 0, 100, 40))

        # 用户消息（含上下留白）1+1+1 + 间隔 padding，assistant 1 行 + 间隔
        assert conversation_sizes[2] == 7
        assert conversation_sizes[4:7] == [3, 0, 2]


def test_input_container_has_border_lines_above_and_below(tmp_path: Path) -> None:
    """测试输入区上下各有一条水平线，不使用灰色背景。"""

    screen = _create_screen(tmp_path)

    top, middle, bottom = screen._input_container.children

    assert middle is screen._input_window
    for line in (top, bottom):
        assert line.height == 1
        style = line.style
        assert "input-border" in style


def test_chat_screen_uses_configured_input_spacing(tmp_path: Path) -> None:
    """测试输入区域使用集中配置的边距和最大行数。"""

    screen = ChatScreen(
        create_status_info("test-model", "暂不可查询", tmp_path),
        input_layout=InputLayoutConfig(
            horizontal_padding=4,
            max_lines=6,
        ),
    )

    assert screen.input_area.window.height.max == 6
    assert screen._input_layout.horizontal_padding == 4


def test_chat_screen_uses_blinking_cursor(tmp_path: Path) -> None:
    """测试输入框启用闪烁光标。"""

    screen = _create_screen(tmp_path)

    assert (
        screen.application.cursor.get_cursor_shape(screen.application)
        == CursorShape.BLINKING_BEAM
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
        == "343541"
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
        if _binding_key(binding) == "c-m" and binding.filter()
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

            return "epsilon"

    status = create_status_info("test-model", "暂不可查询", tmp_path)
    screen = ChatScreen(status, logo_provider=TestLogo())

    assert screen._render_logo() == "epsilon"


def test_chat_screen_page_keys_scroll_conversation(tmp_path: Path) -> None:
    """测试 PageUp/PageDown 会按页滚动对话历史。"""

    screen = ChatScreen(create_status_info("test-model", "暂不可查询", tmp_path))

    class FakeView:
        """记录翻页调用的替身滚动容器。"""

        def __init__(self) -> None:
            self.calls: list[int] = []

        def scroll_page(self, direction: int) -> None:
            self.calls.append(direction)

    screen.conversation_view = FakeView()

    class FakeEvent:
        """提供翻页按键处理器所需的最小应用对象。"""

        app = None

    def invoke(key: str) -> None:
        binding = next(
            binding
            for binding in screen._key_bindings.bindings
            if _binding_key(binding) == key and binding.filter()
        )
        binding.handler(FakeEvent())

    invoke("pageup")
    invoke("pagedown")

    assert screen.conversation_view.calls == [-1, 1]


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


class _FakeDocument:
    """提供补全所需的最小文本接口。"""

    def __init__(self, text: str) -> None:
        self.text_before_cursor = text


def test_slash_command_completer_matches_prefix() -> None:
    """测试 / 前缀输入会按命令名前缀匹配补全。"""

    completer = SlashCommandCompleter(
        [
            ("start-skill", "选择并激活 skill"),
            ("stop-skill", "取消已激活的 skill"),
            ("model", "切换模型"),
        ]
    )

    completions = list(completer.get_completions(_FakeDocument("/start"), None))

    assert [completion.text for completion in completions] == ["start-skill"]
    assert to_plain_text(completions[0].display_meta) == "选择并激活 skill"


def test_slash_command_completer_empty_prefix_lists_all() -> None:
    """测试仅输入 / 时列出全部命令。"""

    completer = SlashCommandCompleter([("model", "切换模型"), ("start-skill", "激活")])

    completions = list(completer.get_completions(_FakeDocument("/"), None))

    assert [completion.text for completion in completions] == ["model", "start-skill"]


def test_slash_command_completer_ignores_plain_text() -> None:
    """测试不以 / 开头的输入不触发补全。"""

    completer = SlashCommandCompleter([("model", "切换模型")])

    assert list(completer.get_completions(_FakeDocument("hello"), None)) == []


def test_layout_includes_bottom_area_with_status(tmp_path: Path) -> None:
    """测试根布局包含底部区域，默认显示状态栏。"""

    screen = _create_screen(tmp_path)

    bottom = screen._layout.container.children[-1]

    assert bottom is screen._bottom_container
    assert screen._bottom_container.children == [screen._status_window]


def test_slash_command_completer_prefers_exact_match() -> None:
    """测试输入与命令完全一致时 exact 匹配排在前。"""

    completer = SlashCommandCompleter(
        [("model-switch", "切换配置"), ("model", "切换模型")]
    )

    completions = list(completer.get_completions(_FakeDocument("/model"), None))

    assert [completion.text for completion in completions] == ["model", "model-switch"]


def test_completion_swaps_bottom_area_to_picker(tmp_path: Path) -> None:
    """测试补全出现时底部区域切换为列表，收起后恢复状态栏。"""

    screen = _create_screen(tmp_path)

    assert screen._command_picker is None
    assert screen._bottom_container.children == [screen._status_window]

    screen._on_completions_changed(_FakeBuffer(["model"]))

    assert screen._command_picker is not None
    assert screen._bottom_container.children == [screen._command_picker.window]

    screen._on_completions_changed(_FakeBuffer([]))

    assert screen._command_picker is None
    assert screen._bottom_container.children == [screen._status_window]


class _FakeCompleteState:
    """模拟补全状态，completions 为文本列表。"""

    def __init__(self, texts: list[str]) -> None:
        self.completions = [
            Completion(text, start_position=0) for text in texts
        ]


class _FakeBuffer:
    """模拟带补全状态的输入缓冲区。"""

    def __init__(self, texts: list[str]) -> None:
        self.complete_state = _FakeCompleteState(texts)


def test_selected_completion_uses_command_picker(tmp_path: Path) -> None:
    """测试选中补全项来自补全列表组件。"""

    screen = _create_screen(tmp_path)
    buffer = screen.input_area.buffer

    assert screen._selected_completion(buffer) is None

    screen._on_completions_changed(_FakeBuffer(["model", "model-switch"]))

    assert screen._selected_completion(buffer).text == "model"

    screen._command_picker.move(1)

    assert screen._selected_completion(buffer).text == "model-switch"


def test_input_text_changed_restarts_completion_after_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试删除字符后重新触发命令补全。"""

    screen = _create_screen(tmp_path)
    started: list[bool] = []
    monkeypatch.setattr(
        screen.input_area.buffer,
        "start_completion",
        lambda: started.append(True),
    )

    screen._last_input_length = 4   # 之前是 /mod
    screen.input_area.buffer.complete_state = None
    screen.input_area.buffer.text = "/mo"
    screen._on_input_text_changed(screen.input_area.buffer)

    assert started == [True]
    assert screen._last_input_length == 3


def test_input_text_changed_skips_when_text_grows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试插入字符（文本变长）不重复触发补全，交给 complete_while_typing。"""

    screen = _create_screen(tmp_path)
    started: list[bool] = []
    monkeypatch.setattr(
        screen.input_area.buffer,
        "start_completion",
        lambda: started.append(True),
    )

    screen._last_input_length = 3
    screen.input_area.buffer.text = "/mod"
    screen._on_input_text_changed(screen.input_area.buffer)

    assert started == []


def test_input_text_changed_skips_without_slash_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试不以 / 开头的输入不触发补全。"""

    screen = _create_screen(tmp_path)
    started: list[bool] = []
    monkeypatch.setattr(
        screen.input_area.buffer,
        "start_completion",
        lambda: started.append(True),
    )

    screen._last_input_length = 5
    screen.input_area.buffer.text = "hello"
    screen._on_input_text_changed(screen.input_area.buffer)

    assert started == []


def test_input_text_changed_dismisses_picker_when_slash_removed(
    tmp_path: Path,
) -> None:
    """测试删除到不以 / 开头时收起残留的补全列表并恢复状态栏。"""

    screen = _create_screen(tmp_path)

    # 先有补全列表显示
    screen._on_completions_changed(_FakeBuffer(["model"]))
    assert screen._command_picker is not None
    assert screen._bottom_container.children == [screen._command_picker.window]

    # 删除到空文本（不再以 / 开头）
    screen._last_input_length = 1
    screen.input_area.buffer.text = ""
    screen._on_input_text_changed(screen.input_area.buffer)

    assert screen._command_picker is None
    assert screen._bottom_container.children == [screen._status_window]


def test_input_text_changed_keeps_picker_while_slash_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试删除后仍以 / 开头时（例如 /mod -> /m）列表保留由补全状态维护。"""

    screen = _create_screen(tmp_path)
    started: list[bool] = []
    monkeypatch.setattr(
        screen.input_area.buffer,
        "start_completion",
        lambda: started.append(True),
    )

    screen._on_completions_changed(_FakeBuffer(["model"]))
    assert screen._command_picker is not None

    screen._last_input_length = 4
    screen.input_area.buffer.text = "/m"
    screen._on_input_text_changed(screen.input_area.buffer)

    # 仍以 / 开头：不主动收起，交由补全状态维护
    assert screen._command_picker is not None
    assert started == [True]


def test_status_model_name_uses_provider(tmp_path: Path) -> None:
    """测试状态栏模型名优先使用动态 provider 的值。"""

    provider_value = "dynamic-model"
    screen = ChatScreen(
        create_status_info("static-model", "n/a", tmp_path),
        model_name_provider=lambda: provider_value,
    )

    fragments = screen._status_rows()
    row2_right = fragments[1][1]

    assert "dynamic-model" in row2_right
    assert "static-model" not in row2_right


def test_status_model_name_falls_back_to_status(tmp_path: Path) -> None:
    """测试未提供 provider 时使用状态对象里的模型名。"""

    screen = ChatScreen(create_status_info("static-model", "n/a", tmp_path))

    row2_right = screen._status_rows()[1][1]

    assert "static-model" in row2_right


def test_status_provider_and_thinking_level_appear(tmp_path: Path) -> None:
    """测试状态栏模型行显示厂商名与推理强度。"""

    screen = ChatScreen(
        create_status_info("deepseek-v4-pro", "n/a", tmp_path),
        provider_name_provider=lambda: "deepseek",
        thinking_level_provider=lambda: "high",
    )

    row2_right = screen._status_rows()[1][1]

    assert "(deepseek) deepseek-v4-pro · high" in row2_right


def test_status_balance_uses_provider(tmp_path: Path) -> None:
    """测试状态栏信息行缺省时优先使用动态余额。"""

    provider_value = "9.99 CNY"
    screen = ChatScreen(
        create_status_info("test-model", "unavailable", tmp_path),
        balance_text_provider=lambda: provider_value,
    )

    row2_left = screen._status_rows()[1][0]

    assert "9.99 CNY" in row2_left
    assert "unavailable" not in row2_left


def test_status_balance_falls_back_to_status(tmp_path: Path) -> None:
    """测试未提供 provider 时使用状态对象里的余额。"""

    screen = ChatScreen(create_status_info("test-model", "2.00 CNY", tmp_path))

    row2_left = screen._status_rows()[1][0]

    assert "2.00 CNY" in row2_left


def test_status_copy_hint_provider(tmp_path: Path) -> None:
    """测试状态栏行一右侧显示复制提示，默认空。"""

    screen = ChatScreen(create_status_info("test-model", "n/a", tmp_path))
    assert screen._status_rows()[0][1] == ""

    hint_screen = ChatScreen(
        create_status_info("test-model", "n/a", tmp_path),
        copy_hint_provider=lambda: "Copied 42 chars to clipboard",
    )
    row1_right = hint_screen._status_rows()[0][1]

    assert row1_right == "Copied 42 chars to clipboard"
