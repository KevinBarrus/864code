"""对话区 Markdown 基础渲染的单元测试。"""

from prompt_toolkit.formatted_text import to_plain_text

from core.markdown import render_inline, render_markdown


def _plain(text: str) -> str:
    """把渲染结果还原为纯文本。"""

    return to_plain_text(render_markdown(text))


def test_heading_uses_heading_style() -> None:
    """测试标题行使用标题样式并去掉井号前缀。"""

    fragments = render_markdown("# 标题")

    assert fragments == [("class:md-heading", "标题")]


def test_bold_and_italic_inline_styles() -> None:
    """测试粗体和斜体使用独立样式。"""

    fragments = render_markdown("这是**粗体**和*斜体*文本")

    assert ("class:md-bold", "粗体") in fragments
    assert ("class:md-italic", "斜体") in fragments
    assert _plain("这是**粗体**和*斜体*文本") == "这是粗体和斜体文本"


def test_unordered_list_keeps_marker() -> None:
    """测试无序列表带圆点前缀。"""

    fragments = render_markdown("- 列表项")

    assert ("", "• ") in fragments
    assert _plain("- 列表项") == "• 列表项"


def test_fenced_code_block_uses_code_style() -> None:
    """测试围栏代码块使用代码块样式。"""

    fragments = render_markdown("```python\nprint(1)\n```")

    assert ("class:md-code-block", "print(1)") in fragments
    assert ("class:md-code-block", "```python") not in fragments


def test_unclosed_code_block_stays_in_code_style() -> None:
    """测试流式输出未闭合的代码块保持代码样式（容错）。"""

    fragments = render_markdown("```python\nprint(1)")

    assert ("class:md-code-block", "print(1)") in fragments


def test_quote_prefix_and_style() -> None:
    """测试引用行带竖线前缀和独立样式。"""

    fragments = render_markdown("> 引用内容")

    assert fragments == [("class:md-quote", "▍ 引用内容")]


def test_horizontal_rule_replaces_dashes() -> None:
    """测试分隔线渲染为一条水平线。"""

    fragments = render_markdown("---")

    assert fragments == [("class:md-hr", "─" * 20)]


def test_plain_text_unchanged() -> None:
    """测试普通文本渲染后内容不变。"""

    assert _plain("你好，这是普通文本。") == "你好，这是普通文本。"


def test_ordered_list_keeps_marker() -> None:
    """测试有序列表保留序号语义。"""

    assert _plain("1. 第一步") == "· 第一步"


def test_unclosed_bold_shows_as_plain_text() -> None:
    """测试流式输出未闭合的粗体标记保持原样。"""

    assert _plain("未闭合**粗体") == "未闭合**粗体"


def test_inline_renders_bold_and_italic() -> None:
    """测试行内渲染函数分别处理粗体和斜体。"""

    fragments = render_inline("a **b** c")

    assert ("class:md-bold", "b") in fragments
