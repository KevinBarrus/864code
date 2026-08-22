"""构造 epsilon 的全屏终端界面。"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal

from prompt_toolkit.application import Application
from prompt_toolkit.completion import Completer, Completion
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
from .command_picker import CommandPicker
from .skill_picker import SkillPicker
from .choice_picker import ChoicePicker
from .input_prompt import InputPrompt
from .tool_approval import ApprovalPrompt
from .tools.permissions import ApprovalResult
from .tools.types import ToolDefinition
from .ui_config import InputLayoutConfig


SubmitHandler = Callable[[str], Awaitable[None]]
ConversationRole = Literal["user", "assistant", "tool"]


class SlashCommandCompleter(Completer):
    """输入 / 后按前缀匹配已注册的 slash command。"""

    def __init__(self, commands: list[tuple[str, str]]) -> None:
        """保存 (命令名, 描述) 列表。"""

        self._commands = list(commands)

    def get_completions(self, document, complete_event):
        """仅当输入以 / 开头时按 exact 优先、prefix 匹配生成补全。"""

        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        prefix = text[1:]
        exact: list[Completion] = []
        prefix_matches: list[Completion] = []
        for name, description in self._commands:
            if name == prefix:
                exact.append(
                    Completion(
                        name,
                        start_position=-len(prefix),
                        display_meta=description,
                    )
                )
            elif name.startswith(prefix):
                prefix_matches.append(
                    Completion(
                        name,
                        start_position=-len(prefix),
                        display_meta=description,
                    )
                )
        yield from exact
        yield from prefix_matches


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
        command_names: list[tuple[str, str]] | None = None,
        model_name_provider: Callable[[], str] | None = None,
        balance_text_provider: Callable[[], str] | None = None,
    ) -> None:
        """创建对话区、输入区和状态栏。"""

        self._status = status
        self._on_submit = on_submit
        self._logo_provider = logo_provider or EmptyLogoProvider()
        self._input_layout = input_layout or InputLayoutConfig()
        self._model_name_provider = model_name_provider
        self._balance_text_provider = balance_text_provider
        self._request_active = False
        self._request_task: asyncio.Task[None] | None = None
        self._submitted_draft: DraftState | None = None
        self._approval_prompt: ApprovalPrompt | None = None
        self._skill_picker: SkillPicker | None = None
        self._choice_picker: ChoicePicker | None = None
        self._text_input: InputPrompt | None = None
        self._command_picker: CommandPicker | None = None
        self._status_message = ""
        self._conversation: list[ConversationEntry] = []
        self._input_history = InMemoryHistory()
        self._last_input_length = 0
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
            completer=SlashCommandCompleter(command_names or []),
            complete_while_typing=True,
        )
        # 删除字符不会触发 complete_while_typing，需要手动重新启动补全
        self.input_area.buffer.on_text_changed += self._on_input_text_changed
        # 补全状态变化时同步底部区域的补全列表
        self.input_area.buffer.on_completions_changed += self._on_completions_changed
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
        self._status_window = Window(
            content=self._status_control,
            height=1,
        )
        bottom_container = HSplit(
            [self._status_window],
            style="class:approval-area",
        )
        self._bottom_container = bottom_container
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
        # 底部区域在输入栏下方：无补全显示状态栏，补全时替换为命令列表（对齐 Codex）
        return HSplit(
            [
                self._logo_container,
                self._conversation_container,
                input_container,
                bottom_container,
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
        items: list[tuple[str, str, str]],
        checked: set[tuple[str, str]],
    ) -> set[tuple[str, str]] | None:
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

    async def request_choice_picker(
        self,
        items: list[str],
        title: str,
        extra_options: list[str] | None = None,
    ) -> str | None:
        """在输入区域显示单选列表并等待用户选择。"""

        picker = ChoicePicker(items, title, extra_options)
        self._choice_picker = picker
        self._input_container.children = [picker.window]
        self._layout.focus(picker.window)
        self.application.invalidate()
        try:
            return await picker.wait()
        finally:
            self._input_container.children = list(self._normal_input_children)
            self._choice_picker = None
            self._layout.focus(self.input_area)
            self.application.invalidate()

    async def request_text_input(
        self,
        title: str,
        is_password: bool = False,
    ) -> str | None:
        """在输入区域显示单行文本输入框并等待用户输入。"""

        prompt = InputPrompt(title, is_password)
        self._text_input = prompt
        self._input_container.children = [prompt.window]
        self._layout.focus(prompt.input_area)
        self.application.invalidate()
        try:
            return await prompt.wait()
        finally:
            self._input_container.children = list(self._normal_input_children)
            self._text_input = None
            self._layout.focus(self.input_area)
            self.application.invalidate()

    def _get_reserved_height(self, width: int, max_height: int) -> int:
        """计算对话视口下方的输入区和底部区域所需高度。"""

        input_height = self._input_container.preferred_height(
            width, max_height
        ).preferred
        bottom_height = self._bottom_container.preferred_height(
            width, max_height
        ).preferred
        return input_height + bottom_height

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
        choice_active = Condition(lambda: self._choice_picker is not None)
        text_input_active = Condition(lambda: self._text_input is not None)
        command_picker_active = Condition(lambda: self._command_picker is not None)
        embedded_active = (
            approval_active | skill_picker_active | choice_active | text_input_active
        )

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

        @key_bindings.add("up", filter=choice_active)
        def move_choice_up(event) -> None:
            """向上移动单选光标。"""

            if self._choice_picker is not None:
                self._choice_picker.move(-1)
                self.application.invalidate()

        @key_bindings.add("down", filter=choice_active)
        def move_choice_down(event) -> None:
            """向下移动单选光标。"""

            if self._choice_picker is not None:
                self._choice_picker.move(1)
                self.application.invalidate()

        @key_bindings.add("enter", filter=choice_active, eager=True)
        def confirm_choice(event) -> None:
            """确认当前单选项目。"""

            if self._choice_picker is not None:
                self._choice_picker.confirm()

        @key_bindings.add("escape", filter=choice_active)
        def cancel_choice(event) -> None:
            """取消单选选择。"""

            if self._choice_picker is not None:
                self._choice_picker.cancel()

        @key_bindings.add("enter", filter=text_input_active, eager=True)
        def confirm_text_input(event) -> None:
            """确认文本输入。"""

            if self._text_input is not None:
                self._text_input.confirm()

        @key_bindings.add("escape", filter=text_input_active)
        def cancel_text_input(event) -> None:
            """取消文本输入。"""

            if self._text_input is not None:
                self._text_input.cancel()

        @key_bindings.add(
            "enter",
            filter=~embedded_active,
            eager=True,
        )
        def submit(event) -> None:
            """提交输入框中的内容，补全列表打开时先应用选中项。"""

            buffer = self.input_area.buffer
            completion = self._selected_completion(buffer)
            if completion is not None:
                buffer.apply_completion(completion)
            prompt = self.input_area.text.strip()
            if not prompt or self._request_active or self._on_submit is None:
                return
            self._submitted_draft = DraftState(
                text=self.input_area.text,
                cursor_position=buffer.cursor_position,
            )
            self._input_history.append_string(self.input_area.text)
            self.input_area.text = ""
            self._request_task = event.app.create_background_task(
                self._submit(prompt)
            )

        @key_bindings.add("up", filter=command_picker_active)
        def move_command_up(event) -> None:
            """向上移动补全列表选中项。"""

            if self._command_picker is not None:
                self._command_picker.move(-1)
                self.application.invalidate()

        @key_bindings.add("down", filter=command_picker_active)
        def move_command_down(event) -> None:
            """向下移动补全列表选中项。"""

            if self._command_picker is not None:
                self._command_picker.move(1)
                self.application.invalidate()

        @key_bindings.add(
            "tab",
            filter=command_picker_active & input_focused & ~embedded_active,
            eager=True,
        )
        def apply_completion(event) -> None:
            """Tab 应用当前补全但不提交（对齐 Codex）。"""

            buffer = self.input_area.buffer
            completion = self._selected_completion(buffer)
            if completion is not None:
                buffer.apply_completion(completion)
                self.application.invalidate()

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
            filter=~embedded_active,
        )
        def cancel_request(event) -> None:
            """取消当前请求，输入恢复由请求任务负责。"""

            self.cancel_request()

        @key_bindings.add("pageup", filter=~embedded_active)
        def page_up(event) -> None:
            """向上翻页滚动对话历史。"""

            self.conversation_view.scroll_page(-1)
            self.application.invalidate()

        @key_bindings.add("pagedown", filter=~embedded_active)
        def page_down(event) -> None:
            """向下翻页滚动对话历史。"""

            self.conversation_view.scroll_page(1)
            self.application.invalidate()

        return key_bindings

    def cancel_request(self) -> None:
        """取消正在运行的模型请求。"""

        if self._request_task is not None and not self._request_task.done():
            self._request_task.cancel()

    def _selected_completion(self, buffer) -> object | None:
        """返回补全列表当前选中的补全项。"""

        if self._command_picker is not None:
            return self._command_picker.selected
        return None

    def _on_completions_changed(self, buffer) -> None:
        """补全状态变化时，在底部区域显示补全列表或恢复状态栏。"""

        state = buffer.complete_state
        completions = list(state.completions) if state is not None else []
        if completions:
            picker = CommandPicker(completions)
            self._command_picker = picker
            self._bottom_container.children = [picker.window]
        else:
            self._command_picker = None
            self._bottom_container.children = [self._status_window]
        self.application.invalidate()

    def _on_input_text_changed(self, buffer) -> None:
        """文本变化时维护命令补全：删字符后重新触发，不再以 / 开头时收起列表。

        注意：prompt_toolkit 的 _text_changed 清空 complete_state 时不会触发
        on_completions_changed，因此删除到非 / 前缀时要显式收起残留的补全列表。
        """

        text = buffer.text
        if not text.startswith("/"):
            # 命令补全不再适用：清除残留列表并恢复状态栏
            if self._command_picker is not None:
                self._command_picker = None
                self._bottom_container.children = [self._status_window]
                self.application.invalidate()
        elif len(text) < self._last_input_length and buffer.complete_state is None:
            buffer.start_completion()
        self._last_input_length = len(text)

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

        model_name = (
            self._model_name_provider()
            if self._model_name_provider is not None
            else self._status.model_name
        )
        balance = (
            self._balance_text_provider()
            if self._balance_text_provider is not None
            else self._status.balance
        )
        fragments = [
            ("class:status-model", f"Model: {model_name}"),
            ("", "    "),
            ("class:status-balance", f"Balance: {balance}"),
            ("", "    "),
            (
                "class:status-working-directory",
                f"Working directory: {self._status.working_directory}",
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
