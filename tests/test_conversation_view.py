from prompt_toolkit.layout import HSplit, Window

from core.conversation_view import ConversationView


def _create_view() -> ConversationView:
    """创建测试用的对话滚动容器。"""

    return ConversationView(HSplit([Window()]))


def test_conversation_view_follows_output_by_default() -> None:
    """测试对话滚动容器默认跟随最新输出。"""

    view = _create_view()

    assert view.follow_output is True


def test_manual_scroll_pauses_following() -> None:
    """测试用户手动滚动后暂停自动跟随。"""

    view = _create_view()
    view.scroll_by(3)

    assert view.follow_output is False
    assert view.vertical_scroll == 3


def test_scroll_to_bottom_resumes_following() -> None:
    """测试回到底部后恢复自动跟随。"""

    view = _create_view()
    view.scroll_by(3)
    view.scroll_to_bottom()

    assert view.follow_output is True


def test_manual_scroll_does_not_pass_content_end() -> None:
    """测试滚动位置不会超过对话内容末尾。"""

    view = _create_view()
    view._max_vertical_scroll = 4

    view.scroll_by(10)

    assert view.vertical_scroll == 4


def test_scrolling_to_current_end_resumes_output_following() -> None:
    """测试滚动到当前末尾后可以继续跟随模型新增内容。"""

    view = _create_view()
    view._max_vertical_scroll = 4
    view.vertical_scroll = 1
    view.scroll_by(10)

    assert view.vertical_scroll == 4
    assert view.follow_output is True


def test_page_scroll_uses_viewport_height() -> None:
    """测试翻页滚动按视口高度移动并暂停自动跟随。"""

    view = _create_view()
    view._viewport_height = 10
    view._max_vertical_scroll = 100

    view.scroll_page(1)

    assert view.vertical_scroll == 9
    assert view.follow_output is False


def test_page_scroll_down_to_bottom_resumes_following() -> None:
    """测试向下翻页到底部后恢复自动跟随。"""

    view = _create_view()
    view._viewport_height = 10
    view._max_vertical_scroll = 5

    view.scroll_page(1)

    assert view.vertical_scroll == 5
    assert view.follow_output is True


def test_page_scroll_up_never_goes_above_top() -> None:
    """测试向上翻页不会越过对话顶部。"""

    view = _create_view()
    view._viewport_height = 10
    view._max_vertical_scroll = 100

    view.scroll_page(-1)

    assert view.vertical_scroll == 0
    assert view.follow_output is False
