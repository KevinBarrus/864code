"""状态栏工具函数与整行渲染的单元测试。"""

from pathlib import Path

from core.screen import ChatScreen, StatusControl
from core.status import create_status_info, format_cwd_for_footer


def test_format_cwd_for_footer_abbreviates_home() -> None:
    """测试 home 目录下的路径缩写为 ~。"""

    home = "/home/kevinbarrus"

    assert (
        format_cwd_for_footer("/home/kevinbarrus/projects/epsilon", home)
        == "~/projects/epsilon"
    )
    assert format_cwd_for_footer("/home/kevinbarrus", home) == "~"


def test_format_cwd_for_footer_keeps_path_outside_home() -> None:
    """测试 home 目录之外的路径保持原样。"""

    assert (
        format_cwd_for_footer("/opt/epsilon", "/home/kevinbarrus")
        == "/opt/epsilon"
    )


def test_status_control_right_aligns_rows() -> None:
    """测试状态栏整行渲染时右侧内容右对齐。"""

    control = StatusControl(
        lambda: [("left", "right"), ("info", "model")]
    )

    content = control.create_content(30, 2)

    row1 = "".join(text for _, text in content.get_line(0))
    row2 = "".join(text for _, text in content.get_line(1))

    assert row1 == "left" + " " * 21 + "right"
    assert row1.endswith("right")
    assert row2.endswith("model")
    assert len(row1) == 30
    assert len(row2) == 30


def test_status_rows_abbreviates_working_directory(tmp_path: Path) -> None:
    """测试状态栏行一显示 ~ 缩写的工作目录。"""

    screen = ChatScreen(
        create_status_info("m", "b", Path.home() / "work" / "epsilon")
    )

    row1_left, _ = screen._status_rows()[0]

    assert row1_left.startswith("~/")
    assert str(Path.home()) not in row1_left
