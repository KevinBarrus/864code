"""集中管理终端界面的颜色和样式。"""

from dataclasses import dataclass

from prompt_toolkit.styles import Style


@dataclass(frozen=True)
class ThemeColors:
    """状态栏各项使用的颜色，可以独立替换而不修改布局代码。"""

    model: str = "#f5d76e"
    balance: str = "#6ec6ff"
    working_directory: str = "#90ee90"


DEFAULT_THEME = ThemeColors()


def create_ui_style(theme: ThemeColors = DEFAULT_THEME) -> Style:
    """根据主题颜色创建 prompt_toolkit 样式。"""

    return Style.from_dict(
        {
            "status-model": f"fg:{theme.model}",
            "status-balance": f"fg:{theme.balance}",
            "status-working-directory": f"fg:{theme.working_directory}",
            "input-area": "bg:#303030",
            "conversation-user": "bg:#303030",
            "approval-area": "bg:#303030",
            "approval-selected": "fg:ansibrightyellow",
            "tool-activity": "fg:#808080",
        }
    )
