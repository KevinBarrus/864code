"""会话选择器（Codex 风格）测试。"""

from datetime import datetime, timedelta, timezone

from core.session_picker import SessionPicker, format_relative_time
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


def test_relative_time_formats() -> None:
    """测试相对时间格式。"""

    now = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    assert format_relative_time(now, now) == "just now"
    assert (
        format_relative_time(now - timedelta(minutes=30), now) == "30m ago"
    )
    assert format_relative_time(now - timedelta(hours=5), now) == "5h ago"
    assert format_relative_time(now - timedelta(days=3), now) == "3d ago"


def test_picker_starts_with_first_session_selected() -> None:
    """测试选择器默认选中第一条会话。"""

    picker = SessionPicker(_summaries())

    rendered = picker._render()

    style, text = rendered[0]
    assert style == "class:selected"
    assert text.startswith("› 第一个会话")
    assert "11111111" in text


def test_picker_renders_zebra_rows() -> None:
    """测试非选中行交替使用底色。"""

    picker = SessionPicker(_summaries())

    rendered = picker._render()

    # 选中行之后的第一行（第二个会话）使用 zebra 底色
    assert rendered[1][0] == "class:zebra"
    assert "第二个会话" in rendered[1][1]


def test_picker_moves_selection_within_bounds() -> None:
    """测试选择移动不会超出列表范围。"""

    picker = SessionPicker(_summaries())

    picker.move_selection(1)
    picker.move_selection(1)
    rendered = picker._render()
    assert rendered[0][0] == ""
    assert rendered[2][0] == "class:selected"

    picker.move_selection(-1)
    picker.move_selection(-1)
    rendered = picker._render()
    assert rendered[0][0] == "class:selected"


def test_picker_filters_by_title() -> None:
    """测试过滤文本按标题缩小列表。"""

    picker = SessionPicker(_summaries())
    picker._filter_text = "第二个"

    assert len(picker._summaries) == 1
    assert picker._summaries[0].title == "第二个会话"


def test_picker_filters_by_session_id() -> None:
    """测试过滤文本可以匹配会话 ID。"""

    picker = SessionPicker(_summaries())
    picker._filter_text = "2222"

    assert [item.title for item in picker._summaries] == ["第二个会话"]


def test_picker_render_shows_no_match_hint() -> None:
    """测试无匹配结果时显示提示。"""

    picker = SessionPicker(_summaries())
    picker._filter_text = "不存在的会话"

    rendered = picker._render()

    assert any("No matching sessions" in text for _, text in rendered)


def test_empty_picker_returns_no_session() -> None:
    """测试没有会话时选择器返回空结果。"""

    picker = SessionPicker([])

    assert picker._all_summaries == []
