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
async def test_choice_picker_move_stays_within_bounds() -> None:
    """测试光标移动不会越过列表边界。"""

    picker = ChoicePicker(["a", "b"], "选择", extra_options=["extra"])

    picker.move(-5)
    picker.confirm()
    assert await picker.wait() == "a"

    picker = ChoicePicker(["a", "b"], "选择", extra_options=["extra"])
    picker.move(10)
    picker.confirm()
    assert await picker.wait() == "extra"
