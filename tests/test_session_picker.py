from datetime import datetime, timezone

from core.session_picker import SessionPicker
from core.session_store import SessionSummary


def _summaries() -> list[SessionSummary]:
    """创建选择器测试数据"""

    return [
        SessionSummary(
            session_id="11111111-1111-1111-1111-111111111111",
            title="第一个会话",
            updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
        SessionSummary(
            session_id="22222222-2222-2222-2222-222222222222",
            title="第二个会话",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    ]


def test_picker_starts_with_first_session_selected() -> None:
    """测试选择器默认选中第一条会话"""

    picker = SessionPicker(_summaries())

    rendered = picker._render()

    assert rendered[1] == ("class:selected", "> 第一个会话")
    assert rendered[3] == ("", "  第二个会话")


def test_picker_moves_selection_within_bounds() -> None:
    """测试选择移动不会超出列表范围"""

    picker = SessionPicker(_summaries())

    picker.move_selection(1)
    picker.move_selection(1)
    rendered = picker._render()
    assert rendered[1] == ("", "  第一个会话")
    assert rendered[3] == ("class:selected", "> 第二个会话")

    picker.move_selection(-1)
    picker.move_selection(-1)
    rendered = picker._render()
    assert rendered[1] == ("class:selected", "> 第一个会话")


def test_picker_renders_selected_and_unselected_styles() -> None:
    """测试只有当前选中项使用蓝色样式"""

    picker = SessionPicker(_summaries())
    picker.move_selection(1)

    rendered = picker._render()

    assert rendered[1][0] == ""
    assert rendered[3][0] == "class:selected"


def test_empty_picker_returns_no_session() -> None:
    """测试没有会话时选择器返回空结果"""

    picker = SessionPicker([])

    assert picker._summaries == []
