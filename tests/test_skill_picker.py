"""测试 skill 勾选选择组件。"""

import pytest

from core.skill_picker import SkillPicker


@pytest.mark.asyncio
async def test_skill_picker_toggles_and_confirms() -> None:
    """测试选择器可以勾选当前项并确认结果。"""

    picker = SkillPicker([("a", "A 描述"), ("b", "B 描述")], checked=set())

    picker.toggle()   # 光标在 a，勾选 a
    picker.move(1)    # 移到 b
    picker.toggle()   # 勾选 b

    picker.confirm()

    assert await picker.wait() == {"a", "b"}


@pytest.mark.asyncio
async def test_skill_picker_untoggles_checked_item() -> None:
    """测试已勾选项可以通过 Space 取消勾选。"""

    picker = SkillPicker([("a", "A"), ("b", "B")], checked={"a", "b"})

    picker.toggle()   # 光标在 a，取消勾选 a
    picker.confirm()

    assert await picker.wait() == {"b"}


@pytest.mark.asyncio
async def test_skill_picker_cancel_returns_none() -> None:
    """测试取消选择返回 None。"""

    picker = SkillPicker([("a", "A")], checked=set())

    picker.cancel()

    assert await picker.wait() is None


@pytest.mark.asyncio
async def test_skill_picker_move_stays_within_bounds() -> None:
    """测试光标移动不会越过列表边界。"""

    picker = SkillPicker([("a", "A")], checked=set())

    picker.move(-5)
    picker.toggle()

    assert picker._checked == {"a"}
