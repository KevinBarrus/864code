"""测试命令补全单选列表组件。"""

from prompt_toolkit.completion import Completion

from core.command_picker import CommandPicker


def _completions(names: list[str]) -> list[Completion]:
    """构造补全项列表。"""

    return [
        Completion(name, start_position=-2, display_meta=f"{name} 的描述")
        for name in names
    ]


def test_command_picker_defaults_to_first_item() -> None:
    """测试默认选中第一项。"""

    picker = CommandPicker(_completions(["model", "start-skill"]))

    assert picker.selected.text == "model"


def test_command_picker_move_wraps_around() -> None:
    """测试光标越界时循环。"""

    picker = CommandPicker(_completions(["model", "start-skill", "stop-skill"]))

    picker.move(-1)   # 顶部向上 → 底部
    assert picker.selected.text == "stop-skill"

    picker.move(2)    # 底部向下 → 第二项
    assert picker.selected.text == "start-skill"


def test_command_picker_renders_name_and_meta() -> None:
    """测试渲染包含命令名与描述。"""

    picker = CommandPicker(_completions(["model"]))

    rendered = "".join(text for _style, text in picker._render())

    assert "/model" in rendered
    assert "model 的描述" in rendered


def test_command_picker_renders_selected_with_prefix() -> None:
    """测试选中项带 › 前缀且使用选中样式。"""

    picker = CommandPicker(_completions(["model", "start-skill"]))

    fragments = picker._render()

    assert fragments[0][0] == "class:approval-selected"
    assert fragments[0][1].startswith("› ")


def test_command_picker_aligns_description_column() -> None:
    """测试描述列左对齐：name 列宽一致，间距拉大。"""

    picker = CommandPicker(
        [
            Completion("model", display_meta="切换模型"),
            Completion("start-skill", display_meta="激活 skill"),
        ]
    )

    fragments = picker._render()

    # 选中行：name 列宽 = max(/model, /start-skill) = 12 + GAP 3
    selected_line = "".join(text for style, text in fragments if text.startswith("›"))
    assert selected_line.startswith("› /model")
    assert "切换模型" in selected_line

    # 未选中行 /start-skill 的描述与选中行描述左对齐（列宽一致）
    all_text = "".join(text for _, text in fragments)
    lines = [line for line in all_text.split("\n") if line.strip()]
    desc_positions = [
        pos for line in lines for pos in (line.find("激活 skill"), line.find("切换模型"))
        if pos != -1
    ]
    assert len(set(desc_positions)) == 1

    # 未选中行的描述使用独立淡灰样式
    description_styles = [
        style
        for style, text in fragments
        if "切换模型" in text or "激活 skill" in text
    ]
    assert "class:completion-description" in description_styles


def test_command_picker_has_no_background_style() -> None:
    """测试补全列表无背景（字体落在终端默认背景）。"""

    picker = CommandPicker(_completions(["model"]))

    assert "approval-area" not in picker.window.style


def test_command_picker_scrolls_to_keep_selection_visible() -> None:
    """测试移动到底部时窗口滚动跟随。"""

    picker = CommandPicker(_completions([f"cmd-{index}" for index in range(20)]))

    picker.move(15)

    assert picker.window.vertical_scroll > 0

    picker = CommandPicker(_completions([f"cmd-{index}" for index in range(20)]))
    picker.move(19)   # 移到最后一个选项
    max_scroll = max(0, 20 - CommandPicker._VISIBLE_ROWS)

    assert picker.window.vertical_scroll == max_scroll
