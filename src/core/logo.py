"""定义会话 Logo 的可替换渲染接口与默认实现。"""

from typing import Protocol

from prompt_toolkit.formatted_text import AnyFormattedText

# ε - EPSILON 方块字（ε 与每个字母 4 列用 █ 拼成，间距 2 空格）
_LOGO_ART = (
    " ████  - ████  ████  ████  █████ █     ████  █  █",
    "█        █     █  █  █       █   █     █  █  ██ █",
    "████  -  ████  ████  ████    █   █     █  █  █ ██",
    "█        █     █        █    █   █     █  █  █  █",
    " ████  - ████  █     ████  █████ ████  ████  █  █",
)




class LogoProvider(Protocol):
    """Logo 渲染实现需要遵循的接口。"""

    def render(self) -> AnyFormattedText:
        """返回要显示在会话顶部的格式化文本。"""


class DefaultLogoProvider:
    """默认 Logo：ε - EPSILON 方块字，使用独立样式类以便主题调整。"""

    def render(self) -> AnyFormattedText:
        """渲染方块字 Logo，后续可替换为专属 Logo。"""

        return [("class:logo-accent", line) for line in _LOGO_ART]
