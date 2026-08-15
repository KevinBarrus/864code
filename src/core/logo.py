"""定义会话 Logo 的可替换渲染接口。"""

from typing import Protocol

from prompt_toolkit.formatted_text import AnyFormattedText


class LogoProvider(Protocol):
    """Logo 渲染实现需要遵循的接口。"""

    def render(self) -> AnyFormattedText:
        """返回要显示在会话顶部的格式化文本。"""


class EmptyLogoProvider:
    """默认的空 Logo 实现。"""

    def render(self) -> str:
        """暂时不显示 Logo。"""

        return ""
