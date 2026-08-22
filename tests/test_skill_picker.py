"""测试 skill 勾选选择组件。"""

import pytest

from core.skill_picker import SkillPicker


@pytest.mark.asyncio
async def test_skill_picker_toggles_and_confirms() -> None:
    """测试选择器可以勾选当前项并确认结果。"""

    picker = SkillPicker(
        [("a", "A 描述", "project"), ("b", "B 描述", "global")],
        checked=set(),
    )

    picker.toggle()   # 光标在 a，勾选 ("a", "project")
    picker.move(1)    # 移到 b
    picker.toggle()   # 勾选 ("b", "global")

    picker.confirm()

    assert await picker.wait() == {("a", "project"), ("b", "global")}


@pytest.mark.asyncio
async def test_skill_picker_untoggles_checked_item() -> None:
    """测试已勾选项可以通过 Space 取消勾选。"""

    picker = SkillPicker(
        [("a", "A", "project"), ("b", "B", "global")],
        checked={("a", "project"), ("b", "global")},
    )

    picker.toggle()   # 光标在 a，取消勾选 a
    picker.confirm()

    assert await picker.wait() == {("b", "global")}


@pytest.mark.asyncio
async def test_skill_picker_keeps_duplicate_names_distinct_by_source() -> None:
    """测试同名不同来源的 skill 可独立勾选。"""

    picker = SkillPicker(
        [("git", "项目版", "project"), ("git", "全局版", "global")],
        checked=set(),
    )

    picker.toggle()   # 勾选 ("git", "project")
    picker.move(1)
    picker.toggle()   # 勾选 ("git", "global")

    picker.confirm()

    assert await picker.wait() == {("git", "project"), ("git", "global")}


@pytest.mark.asyncio
async def test_skill_picker_cancel_returns_none() -> None:
    """测试取消选择返回 None。"""

    picker = SkillPicker([("a", "A", "project")], checked=set())

    picker.cancel()

    assert await picker.wait() is None


@pytest.mark.asyncio
async def test_skill_picker_move_wraps_around() -> None:
    """测试光标越界时循环到另一端。"""

    picker = SkillPicker(
        [("a", "A", "project"), ("b", "B", "global")],
        checked=set(),
    )

    picker.move(-1)   # 从顶部 a 向上 → 底部 b
    picker.toggle()

    assert picker._checked == {("b", "global")}

    picker.move(1)    # 从底部 b 向下 → 顶部 a
    picker.toggle()

    assert picker._checked == {("a", "project"), ("b", "global")}


@pytest.mark.asyncio
async def test_skill_picker_renders_source_suffix() -> None:
    """测试渲染结果包含来源后缀。"""

    picker = SkillPicker(
        [("grill-me", "提问练习", "project"), ("teach", "教学", "global")],
        checked=set(),
    )

    rendered = "".join(item[1] for item in picker._render())

    assert "grill-me [projects]" in rendered
    assert "teach [global]" in rendered


@pytest.mark.asyncio
async def test_skill_picker_click_toggles_check() -> None:
    """测试鼠标点击某行选中并切换勾选。"""

    picker = SkillPicker(
        [("grill-me", "提问练习", "project")],
        checked=set(),
    )
    fragments = picker._render()
    handler = None
    for item in fragments:
        if "[ ]" in item[1] and "grill-me" in item[1]:
            handler = item[2]
            break
    assert handler is not None
    handler(None)

    assert ("grill-me", "project") in picker._checked
