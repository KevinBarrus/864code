from core.theme import DEFAULT_THEME, ThemeColors, create_ui_style


def test_default_theme_contains_status_colors() -> None:
    """测试默认主题为三类状态栏信息提供独立颜色。"""

    assert DEFAULT_THEME.model
    assert DEFAULT_THEME.balance
    assert DEFAULT_THEME.working_directory


def test_create_ui_style_uses_custom_theme_colors() -> None:
    """测试修改主题配置后，界面样式会使用新的颜色。"""

    theme = ThemeColors(model="#111111", balance="#222222", working_directory="#333333")

    style = create_ui_style(theme)

    assert style.get_attrs_for_style_str("class:status-model").color == "111111"
    assert style.get_attrs_for_style_str("class:status-balance").color == "222222"
    assert (
        style.get_attrs_for_style_str("class:status-working-directory").color
        == "333333"
    )
