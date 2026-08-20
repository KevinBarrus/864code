"""构造 epsilon 的全屏终端界面。"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal

from prompt_toolkit.application import Application
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.formatted_text import AnyFormattedText, to_plain_text
from prompt_toolkit.filters import has_focus
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    VerticalAlign,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.filters import Condition
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from .status import StatusInfo
from .theme import create_ui_style
from .logo import EmptyLogoProvider, LogoProvider
from .conversation_view import ConversationView
from .model import ToolCall
from .skill_picker import SkillPicker
from .tool_approval import ApprovalPrompt
from .tools.permissions import ApprovalResult
from .tools.types import ToolDefinition
from .ui_config import InputLayoutConfig


SubmitHandler = Callable[[str], Awaitable[None]]
ConversationRole = Literal["user", "assistant", "tool"]


@dataclass(frozen=True)
class ConversationEntry:
    """对话区中的一条展示内容。"""

    role: ConversationRole
    content: str
    control: FormattedTextControl


@dataclass(frozen=True)
class DraftState:
    """发送前输入框中的文字和光标位置。"""

    text: str
    cursor_position: int


class ChatScreen:
    """管理全屏界面的静态布局和可展示内容。"""

    def __init__(
        self,
        status: StatusInfo,
        style: Style | None = None,
        on_submit: SubmitHandler | None = None,
        logo_provider: LogoProvider | None = None,
        input_layout: InputLayoutConfig | None = None,
    ) -> None:
        """创建对话区、输入区和状态栏。"""

        self._status = status
        self._on_submit = on_submit
        self._logo_provider = logo_provider or EmptyLogoProvider()
        self._input_layout = input_layout or InputLayoutConfig()
        self._request_active = False
        self._request_task: asyncio.Task[None] | None = None
        self._submitted_draft: DraftState | None = None
        self._approval_prompt: ApprovalPrompt | None = None
        self._skill_picker: SkillPicker | None = None
        self._status_message = ""
        self._conversation: list[ConversationEntry] = []
        self._input_history = InMemoryHistory()
        self.input_area = TextArea(
            prompt="",
            multiline=True,
            wrap_lines=True,
            scrollbar=False,
            height=Dimension(min=1, max=self._input_layout.max_lines),
            dont_extend_height=True,
            focus_on_click=True,
            style="class:input-area",
            get_line_prefix=self._get_input_line_prefix,
            history=self._input_history,
        )
        self._conversation_content = HSplit(
            [],
            # 不添加顶部对齐的隐式填充行，消息内容只占实际需要的高度。
            align=VerticalAlign.JUSTIFY,
            padding=1,
        )
        self.conversation_view = ConversationView(
            self._conversation_content,
            reserved_height=self._get_reserved_height,
        )
        self._logo_control = FormattedTextControl(self._render_logo, focusable=False)
        self._status_control = FormattedTextControl(
            self._render_status,
            focusable=False,
        )
        self._layout = Layout(
            self._create_layout(),
            focused_element=self.input_area,
        )
        self._key_bindings = self._create_key_bindings()
        self.application = Application(
            layout=self._layout,
            key_bindings=self._key_bindings,
            style=style or create_ui_style(),
            full_screen=True,
            mouse_support=True,
            cursor=CursorShape.BLINKING_BEAM,
        )

    def add_entry(self, role: ConversationRole, content: str) -> int:
        """向对话区追加一条展示内容，并返回它的索引。"""

        self._conversation.append(self._create_entry(role, content))
        self._sync_conversation_view()
        if role == "user":
            self.conversation_view.scroll_to_bottom()
        self.application.invalidate()
        return len(self._conversation) - 1

    def add_history_entries(
        self,
        entries: list[tuple[ConversationRole, str]],
    ) -> None:
        """批量追加恢复历史，并只同步一次对话布局。"""

        if not entries:
            return
        self._conversation.extend(
            self._create_entry(role, content) for role, content in entries
        )
        self._sync_conversation_view()
        self.conversation_view.scroll_to_bottom()
        self.application.invalidate()

    @staticmethod
    def _create_entry(role: ConversationRole, content: str) -> ConversationEntry:
        """创建保存独立文本控件的对话条目。"""

        return ConversationEntry(
            role,
            content,
            FormattedTextControl(content, focusable=False),
        )

    def append_to_entry(self, index: int, content: str) -> None:
        """向指定的对话条目追加流式文本。"""

        entry = self._conversation[index]
        self._set_entry_content(index, entry.content + content)
        self.application.invalidate()

    def set_entry_content(self, index: int, content: str) -> None:
        """替换指定对话条目的展示内容。"""

        self._set_entry_content(index, content)
        self.application.invalidate()

    def _set_entry_content(self, index: int, content: str) -> None:
        """更新已有条目的内容和控件，不重建整个对话布局。"""

        entry = self._conversation[index]
        entry.control.text = content
        entry.control.reset()
        self._conversation[index] = replace(entry, content=content)

    def set_request_active(self, active: bool) -> None:
        """更新请求状态，避免模型响应期间重复提交。"""

        self._request_active = active

    def copy_input_selection(self) -> None:
        """复制输入框中选中的文本，没有选区时不执行操作。"""

        buffer = self.input_area.buffer
        if buffer.selection_state is None:
            return
        self.application.clipboard.set_data(buffer.copy_selection())

    def paste_to_input(self) -> None:
        """将剪贴板内容粘贴到输入框当前位置。"""

        self.input_area.buffer.paste_clipboard_data(
            self.application.clipboard.get_data()
        )

    def _create_layout(self) -> HSplit:
        """创建对话区、输入区和状态栏的垂直布局。"""

        logo_window = Window(
            content=self._logo_control,
            height=Dimension(min=0),
            wrap_lines=True,
            dont_extend_height=True,
        )
        self._logo_container = ConditionalContainer(
            logo_window,
            filter=Condition(self._has_logo),
        )
        self._conversation_container = ConditionalContainer(
            self.conversation_view,
            filter=Condition(lambda: bool(self._conversation)),
        )
        status_window = Window(
            content=self._status_control,
            height=1,
        )
        input_container = HSplit(
            [
                Window(
                    height=self._input_layout.vertical_padding,
                    style="class:input-area",
                ),
                self.input_area,
                Window(
                    height=self._input_layout.vertical_padding,
                    style="class:input-area",
                ),
            ],
            # TOP 会为剩余空间添加一个继承灰色背景的填充窗口；
            # 输入区必须只占上下留白和文字实际需要的高度。
            align=VerticalAlign.JUSTIFY,
            style="class:input-area",
            width=Dimension(weight=1),
        )
        self._input_container = input_container
        self._normal_input_children = list(input_container.children)
        # TextArea 自身已经限制了最大高度，直接把 HSplit 放入根布局，
        # 避免用 Window 错误地包裹 Container，导致焦点控件无法被找到。
        self._input_window = self.input_area.window
        return HSplit(
            [
                self._logo_container,
                self._conversation_container,
                input_container,
                status_window,
            ],
            # 不使用 TOP，避免 prompt_toolkit 自动追加一个无样式的
            # 填充窗口；剩余空间应当只交给有消息时的对话视口。
            align=VerticalAlign.JUSTIFY,
        )

    async def request_approval(
        self,
        definition: ToolDefinition,
        tool_call: ToolCall,
        allow_session: bool = True,
    ) -> ApprovalResult:
        """在输入区域显示审批选项并等待用户选择。"""

        prompt = ApprovalPrompt(definition, tool_call, allow_session)
        self._approval_prompt = prompt
        self._input_container.children = [prompt.window]
        self._layout.focus(prompt.window)
        self.application.invalidate()
        try:
            return await prompt.wait()
        finally:
            self._input_container.children = list(self._normal_input_children)
            self._approval_prompt = None
            self._layout.focus(self.input_area)
            self.application.invalidate()

    async def request_skill_picker(
        self,
        items: list[tuple[str, str]],
        checked: set[str],
    ) -> set[str] | None:
        """在输入区域显示 skill 勾选列表并等待用户选择。"""

        picker = SkillPicker(items, checked)
        self._skill_picker = picker
        self._input_container.children = [picker.window]
        self._layout.focus(picker.window)
        self.application.invalidate()
        try:
            return await picker.wait()
        finally:
            self._input_container.children = list(self._normal_input_children)
            self._skill_picker = None
            self._layout.focus(self.input_area)
            self.application.invalidate()

    def _get_reserved_height(self, width: int, max_height: int) -> int:
        """计算对话视口下方的输入区和状态栏所需高度。"""

        return self._input_container.preferred_height(width, max_height).preferred + 1

    def _has_logo(self) -> bool:
        """判断 Logo 是否有实际内容，空 Logo 不占用布局空间。"""

        return bool(to_plain_text(self._logo_provider.render()).strip())

    def _get_input_line_prefix(self, lineno: int, wrap_count: int):
        """为输入文字提供可配置的左右内边距和 > 前缀。"""

        padding = " " * self._input_layout.horizontal_padding
        if lineno == 0 and wrap_count == 0:
            return [("", f"{padding}> ")]
        return [("", f"{padding}  ")]

    def _create_key_bindings(self) -> KeyBindings:
        """创建提交、换行和退出快捷键。"""

        key_bindings = KeyBindings()
        input_focused = has_focus(self.input_area.buffer)
        approval_active = Condition(lambda: self._approval_prompt is not None)
        skill_picker_active = Condition(lambda: self._skill_picker is not None)

        @key_bindings.add("up", filter=approval_active)
        def move_approval_up(event) -> None:
            """向上移动审批选项。"""

            if self._approval_prompt is not None:
                self._approval_prompt.move(-1)
                self.application.invalidate()

        @key_bindings.add("down", filter=approval_active)
        def move_approval_down(event) -> None:
            """向下移动审批选项。"""

            if self._approval_prompt is not None:
                self._approval_prompt.move(1)
                self.application.invalidate()

        @key_bindings.add("enter", filter=approval_active, eager=True)
        def confirm_approval(event) -> None:
            """确认当前审批选项。"""

            if self._approval_prompt is not None:
                self._approval_prompt.confirm()

        @key_bindings.add("escape", filter=approval_active)
        def reject_approval(event) -> None:
            """取消审批并拒绝工具调用。"""

            if self._approval_prompt is not None:
                self._approval_prompt.reject()

        @key_bindings.add("up", filter=skill_picker_active)
        def move_skill_up(event) -> None:
            """向上移动 skill 选择。"""

            if self._skill_picker is not None:
                self._skill_picker.move(-1)
                self.application.invalidate()

        @key_bindings.add("down", filter=skill_picker_active)
        def move_skill_down(event) -> None:
            """向下移动 skill 选择。"""

            if self._skill_picker is not None:
                self._skill_picker.move(1)
                self.application.invalidate()

        @key_bindings.add("space", filter=skill_picker_active)
        def toggle_skill(event) -> None:
            """切换当前 skill 的勾选状态。"""

            if self._skill_picker is not None:
                self._skill_picker.toggle()
                self.application.invalidate()

        @key_bindings.add("enter", filter=skill_picker_active, eager=True)
        def confirm_skill(event) -> None:
            """确认当前勾选的 skill 集合。"""

            if self._skill_picker is not None:
                self._skill_picker.confirm()

        @key_bindings.add("escape", filter=skill_picker_active)
        def cancel_skill(event) -> None:
            """取消 skill 选择。"""

            if self._skill_picker is not None:
                self._skill_picker.cancel()

        @key_bindings.add(
            "enter",
            filter=~approval_active & ~skill_picker_active,
            eager=True,
        )
        def submit(event) -> None:
            """提交输入框中的内容。"""

            prompt = self.input_area.text.strip()
            if not prompt or self._request_active or self._on_submit is None:
                return
            self._submitted_draft = DraftState(
                text=self.input_area.text,
                cursor_position=self.input_area.buffer.cursor_position,
            )
            self._input_history.append_string(self.input_area.text)
            self.input_area.text = ""
            self._request_task = event.app.create_background_task(
                self._submit(prompt)
            )

        @key_bindings.add("c-j", filter=input_focused)
        def insert_newline(event) -> None:
            """使用兼容快捷键在输入框中插入换行。"""

            # 普通终端通常无法区分 Ctrl+Enter 和 Enter，因此使用 Ctrl+J 作为可靠备用键。
            event.current_buffer.insert_text("\n")

        @key_bindings.add("c-d")
        def exit_application(event) -> None:
            """使用 Ctrl+D 退出全屏界面。"""

            event.app.exit()

        @key_bindings.add("c-c", filter=input_focused)
        def copy_selection(event) -> None:
            """复制输入框中的选中文本。"""

            self.copy_input_selection()

        @key_bindings.add("c-v", filter=input_focused)
        @key_bindings.add("s-insert", filter=input_focused)
        def paste_clipboard(event) -> None:
            """将剪贴板内容粘贴到输入框。"""

            self.paste_to_input()

        @key_bindings.add(
            "escape",
            filter=~approval_active & ~skill_picker_active,
        )
        def cancel_request(event) -> None:
            """取消当前请求，输入恢复由请求任务负责。"""

            self.cancel_request()

        @key_bindings.add("pageup", filter=~approval_active)
        def page_up(event) -> None:
            """向上翻页滚动对话历史。"""

            self.conversation_view.scroll_page(-1)
            self.application.invalidate()

        @key_bindings.add("pagedown", filter=~approval_active)
        def page_down(event) -> None:
            """向下翻页滚动对话历史。"""

            self.conversation_view.scroll_page(1)
            self.application.invalidate()

        return key_bindings

    def cancel_request(self) -> None:
        """取消正在运行的模型请求。"""

        if self._request_task is not None and not self._request_task.done():
            self._request_task.cancel()

    async def _submit(self, prompt: str) -> None:
        """标记请求状态并调用应用层提交处理器。"""

        if self._on_submit is None:
            return
        self._request_active = True
        try:
            await self._on_submit(prompt)
        except asyncio.CancelledError:
            self._restore_submitted_draft()
        finally:
            self._request_active = False
            self._request_task = None
            self._submitted_draft = None

    def _restore_submitted_draft(self) -> None:
        """恢复请求发送前的输入文本和光标位置。"""

        if self._submitted_draft is None:
            return

        draft = self._submitted_draft
        self.input_area.buffer.text = draft.text
        self.input_area.buffer.cursor_position = min(
            draft.cursor_position,
            len(draft.text),
        )
        self.application.invalidate()

    def _render_entry(self, index: int) -> str:
        """返回对话条目的纯文本，不添加角色前缀。"""

        return self._conversation[index].content

    def _render_logo(self) -> AnyFormattedText:
        """调用 Logo 接口，预留未来的个人 Logo。"""

        return self._logo_provider.render()

    def _sync_conversation_view(self) -> None:
        """将对话数据同步到带样式的可滚动视图。"""

        children: list[Window] = []
        for index, entry in enumerate(self._conversation):
            if entry.role == "user":
                style = "class:conversation-user"
            elif entry.role == "tool":
                style = "class:tool-activity"
            else:
                style = ""
            children.append(
                Window(
                    content=entry.control,
                    style=style,
                    wrap_lines=True,
                    dont_extend_height=True,
                )
            )
        self._conversation_content.children = children

        for child in children:
            child.content.mouse_handler = self.conversation_view.handle_mouse_event

    def _render_status(self) -> list[tuple[str, str]]:
        """将状态信息转换为带独立颜色的底部状态栏。"""

        fragments = [
            ("class:status-model", f"模型：{self._status.model_name}"),
            ("", "    "),
            ("class:status-balance", f"余额：{self._status.balance}"),
            ("", "    "),
            (
                "class:status-working-directory",
                f"工作目录：{self._status.working_directory}",
            ),
        ]
        if self._status_message:
            fragments.extend(
                [("", "    "), ("class:status-error", self._status_message)]
            )
        return fragments

    def set_status_message(self, message: str) -> None:
        """更新状态栏中的运行时提示。"""

        self._status_message = message
        self.application.invalidate()
