"""测试单选选择组件。"""

import pytest

from core.choice_picker import ChoicePicker


@pytest.mark.asyncio
async def test_choice_picker_confirm_returns_cursor_item() -> None:
    """测试确认返回当前光标项。"""

    picker = ChoicePicker(["a", "b", "c"], "选择")

    picker.move(1)
    picker.confirm()

    assert await picker.wait() == "b"


@pytest.mark.asyncio
async def test_choice_picker_extra_options_are_appendable() -> None:
    """测试尾部特殊选项可以移动到并选中。"""

    picker = ChoicePicker(["a", "b"], "选择", extra_options=["new config"])

    picker.move(2)   # 移到 new config
    picker.confirm()

    assert await picker.wait() == "new config"


@pytest.mark.asyncio
async def test_choice_picker_multiple_extra_options() -> None:
    """测试可以附加多个尾部特殊选项。"""

    picker = ChoicePicker(
        ["a"],
        "选择",
        extra_options=["new config", "manual input"],
    )

    picker.move(2)
    picker.confirm()

    assert await picker.wait() == "manual input"


@pytest.mark.asyncio
async def test_choice_picker_cancel_returns_none() -> None:
    """测试取消返回 None。"""

    picker = ChoicePicker(["a"], "选择")

    picker.cancel()

    assert await picker.wait() is None


@pytest.mark.asyncio
async def test_choice_picker_move_wraps_around() -> None:
    """测试光标越界时循环到另一端。"""

    picker = ChoicePicker(["a", "b", "c"], "选择")

    picker.move(-1)   # 从顶部向上 → 底部
    picker.confirm()
    assert await picker.wait() == "c"

    picker = ChoicePicker(["a", "b", "c"], "选择")
    picker.move(3)    # 从底部向下 → 顶部
    picker.confirm()
    assert await picker.wait() == "a"

    picker = ChoicePicker(["a", "b"], "选择", extra_options=["extra"])
    picker.move(10)   # 多次循环
    picker.confirm()
    assert await picker.wait() == "b"


@pytest.mark.asyncio
async def test_choice_picker_scrolls_to_keep_cursor_visible() -> None:
    """测试光标移动到列表深处时窗口滚动跟随。"""

    picker = ChoicePicker([f"item-{index}" for index in range(20)], "选择")

    picker.move(10)

    assert picker.window.vertical_scroll > 0
    assert picker._cursor == 10


@pytest.mark.asyncio
async def test_choice_picker_wraps_and_follows_scroll() -> None:
    """测试越过末尾后循环回顶部并重置滚动，滚动跟随保持。"""

    picker = ChoicePicker([f"item-{index}" for index in range(20)], "选择")

    picker.move(25)   # 0 + 25 = 25 % 20 = 5
    assert picker._cursor == 5
    assert picker.window.vertical_scroll == 0

    picker.move(15)   # 5 + 15 = 20 % 20 = 0，回到顶部
    assert picker._cursor == 0
    assert picker.window.vertical_scroll == 0


@pytest.mark.asyncio
async def test_choice_picker_renders_selected_with_prefix() -> None:
    """测试选中项用 › 前缀且不显示圆圈。"""

    picker = ChoicePicker(["a", "b"], "选择")

    fragments = picker._render()

    rendered = "".join(item[1] for item in fragments)
    assert "› a" in rendered
    assert "  b" in rendered
    assert "●" not in rendered
    assert "○" not in rendered
    assert any(
        item[0] == "class:approval-selected" and "›" in item[1]
        for item in fragments
    )


@pytest.mark.asyncio
async def test_choice_picker_click_selects_and_confirms() -> None:
    """测试鼠标点击某行立即选中并确认。"""

    picker = ChoicePicker(["a", "b", "c"], "选择")
    fragments = picker._render()
    # 找到第二行（b）的鼠标处理器并触发
    handler = None
    for item in fragments:
        if item[1].startswith("  b"):
            handler = item[2]
            break
    assert handler is not None
    handler(None)

    assert await picker.wait() == "b"
