"""Logo 默认实现与起始信息合并的单元测试。"""

from prompt_toolkit.formatted_text import to_plain_text

from core.logo import DefaultLogoProvider


def test_default_logo_renders_name_and_version() -> None:
    """测试默认 Logo 渲染项目名与版本号。"""

    logo = DefaultLogoProvider().render()

    text = to_plain_text(logo)

    assert "epsilon" in text
    assert "v" in text


def test_default_logo_uses_accent_style() -> None:
    """测试项目名使用独立样式类。"""

    logo = DefaultLogoProvider().render()

    assert ("class:logo-accent", "epsilon") in logo
