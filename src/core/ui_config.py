"""集中管理终端界面的尺寸配置。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class InputLayoutConfig:
    """输入区域的内边距和高度配置。"""

    horizontal_padding: int = 2
    vertical_padding: int = 1
    max_lines: int = 8
