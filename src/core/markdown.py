"""对话区 Markdown 基础渲染：标题、粗体、斜体、列表、代码块、引用、分隔线。"""

import re

from prompt_toolkit.formatted_text import StyleAndTextTuples

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_HR_RE = re.compile(r"^\s*([-*_])\s*\1\s*\1\s*$")
_LIST_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_ORDERED_LIST_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")
_CODE_BLOCK_DELIMITER = "```"


def render_markdown(text: str) -> StyleAndTextTuples:
    """把基础 Markdown 文本转换为带样式的片段列表。

    流式输出时文本可能不完整，解析器对未闭合的代码块/标记保持容错。
    """

    fragments: StyleAndTextTuples = []
    in_code_block = False
    for line in text.split("\n"):
        if in_code_block:
            if line.strip().startswith(_CODE_BLOCK_DELIMITER):
                in_code_block = False
            else:
                fragments.append(("class:md-code-block", line))
            continue
        if line.strip().startswith(_CODE_BLOCK_DELIMITER):
            in_code_block = True
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            fragments.append(("class:md-heading", heading.group(2)))
            continue
        if _HR_RE.match(line):
            fragments.append(("class:md-hr", "─" * 20))
            continue
        quote = _QUOTE_RE.match(line)
        if quote:
            fragments.append(("class:md-quote", f"▍ {quote.group(1)}"))
            continue
        list_match = _LIST_RE.match(line)
        if list_match:
            fragments.extend([("", "• "), *render_inline(list_match.group(1))])
            continue
        ordered_match = _ORDERED_LIST_RE.match(line)
        if ordered_match:
            fragments.extend([("", "· "), *render_inline(ordered_match.group(1))])
            continue
        fragments.extend(render_inline(line))
    return fragments


def render_inline(text: str) -> StyleAndTextTuples:
    """把一行内的粗体和斜体标记转换为带样式的片段。"""

    fragments: StyleAndTextTuples = []
    for part in _INLINE_RE.split(text):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            fragments.append(("class:md-bold", part[2:-2]))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            fragments.append(("class:md-italic", part[1:-1]))
        elif part:
            fragments.append(("", part))
    return fragments
