"""集中管理终端界面的尺寸配置。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class InputLayoutConfig:
    """输入区域的尺寸配置。"""

    max_lines: int = 8
