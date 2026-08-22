from core.theme import create_ui_style


def test_ui_style_status_bar_is_dim_gray() -> None:
    """测试状态栏使用统一的淡灰前景色。"""

    style = create_ui_style()

    assert style.get_attrs_for_style_str("class:status-bar").color == "666666"


def test_ui_style_has_no_approval_background() -> None:
    """测试底部区域不再使用灰色背景（对齐 Pi，字体落在默认背景）。"""

    style = create_ui_style()

    assert not style.get_attrs_for_style_str("class:approval-area").bgcolor


def test_ui_style_keeps_markdown_and_tool_colors() -> None:
    """测试 Markdown 与工具三色样式保留。"""

    style = create_ui_style()

    assert style.get_attrs_for_style_str("class:tool-pending").bgcolor == "282832"
    assert style.get_attrs_for_style_str("class:tool-success").bgcolor == "283228"
    assert style.get_attrs_for_style_str("class:tool-error").bgcolor == "3c2828"
    assert style.get_attrs_for_style_str("class:md-heading").color == "f5d76e"
