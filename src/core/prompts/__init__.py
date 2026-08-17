"""加载上下文管理使用的提示词资源。"""

from functools import lru_cache
from importlib import resources


class PromptLoadError(ValueError):
    """提示词资源不存在或内容为空时抛出的异常。"""


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """读取并缓存指定名称的 Markdown 提示词。"""

    if not name or "/" in name or "\\" in name:
        raise PromptLoadError("提示词名称无效")

    resource = resources.files(__name__).joinpath(f"{name}.md")
    try:
        content = resource.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise PromptLoadError(f"提示词不存在：{name}") from exc
    if not content:
        raise PromptLoadError(f"提示词内容为空：{name}")
    return content
