"""集中管理终端界面的颜色和样式。"""

from prompt_toolkit.styles import Style


def create_ui_style() -> Style:
    """创建 prompt_toolkit 样式。"""

    return Style.from_dict(
        {
            # 状态栏统一淡灰（对齐 Pi footer dim）
            "status-bar": "fg:#666666",
            # 起始信息：Logo 与操作提示
            "logo-accent": "bold #f5d76e",
            "startup-hint": "fg:#666666",
            "startup-context-header": "bold #f5d76e",
            # 输入区上下水平线（对齐 Pi DynamicBorder）
            "input-border": "fg:#5f87ff",
            "conversation-user": "bg:#343541",
            "approval-selected": "fg:ansibrightcyan",
            "completion-description": "fg:#808080",
            "tool-activity": "fg:#808080",
            # 工具调用三色背景（对齐 Pi tool-execution.ts）
            "tool-pending": "bg:#282832",
            "tool-success": "bg:#283228",
            "tool-error": "bg:#3c2828",
            # Markdown 基础渲染样式
            "md-heading": "bold #f5d76e",
            "md-bold": "bold",
            "md-italic": "italic",
            "md-code": "bg:#2d2d2d",
            "md-code-block": "bg:#2d2d2d fg:#a0a0a0",
            "md-link": "fg:#81a2be",
            "md-table-header": "bold",
            "md-quote": "fg:#808080",
            "md-hr": "fg:#505050",
        }
    )
