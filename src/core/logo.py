"""定义会话 Logo 的可替换渲染接口与默认实现。"""

from importlib.metadata import PackageNotFoundError, version
from typing import Protocol

from prompt_toolkit.formatted_text import AnyFormattedText


class LogoProvider(Protocol):
    """Logo 渲染实现需要遵循的接口。"""

    def render(self) -> AnyFormattedText:
        """返回要显示在会话顶部的格式化文本。"""


class DefaultLogoProvider:
    """默认 Logo：项目名与版本号，后续可替换为专属 Logo。"""

    def render(self) -> AnyFormattedText:
        """渲染项目名与版本号，使用独立样式类以便主题调整。"""

        try:
            app_version = version("epsilon")
        except PackageNotFoundError:
            app_version = "0.1.0"
        return [
            ("class:logo-accent", "epsilon"),
            ("", f" v{app_version}"),
        ]
