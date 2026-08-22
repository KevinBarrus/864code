"""对话区 Markdown 渲染：标题、粗体、斜体、列表、代码块、引用、分隔线、行内代码、链接、表格。"""

import re

from prompt_toolkit.formatted_text import StyleAndTextTuples
from wcwidth import wcswidth

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_HR_RE = re.compile(r"^\s*([-*_])\s*\1\s*\1\s*$")
_LIST_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_ORDERED_LIST_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_INLINE_RE = re.compile(
    r"(`[^`]+`|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|\*[^*]+\*)"
)
_LINK_RE = re.compile(r"^\[([^\]]+)\]\([^)]+\)$")
_CODE_BLOCK_DELIMITER = "```"
_TABLE_CELL_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^[\s:|-]+$")


def render_markdown(text: str) -> StyleAndTextTuples:
    """把 Markdown 文本转换为带样式的片段列表，行与行之间插入换行。

    流式输出时文本可能不完整，解析器对未闭合的代码块/标记保持容错。
    """

    fragments: StyleAndTextTuples = []
    in_code_block = False
    table_rows: list[list[str]] | None = None
    lines = text.split("\n")
    for line_index, line in enumerate(lines):
        is_last = line_index == len(lines) - 1
        add_newline = not is_last
        if in_code_block:
            if line.strip().startswith(_CODE_BLOCK_DELIMITER):
                in_code_block = False
            else:
                fragments.append(("class:md-code-block", line))
        elif line.strip().startswith(_CODE_BLOCK_DELIMITER):
            in_code_block = True
        elif _TABLE_CELL_RE.match(line):
            # 表格行由整表渲染统一换行，不在行内单独插入
            add_newline = False
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if table_rows is None:
                table_rows = [cells]
            else:
                table_rows.append(cells)
        else:
            if table_rows is not None:
                fragments.extend(_render_table(table_rows))
                fragments.append(("", "\n"))
                table_rows = None
            heading = _HEADING_RE.match(line)
            if heading:
                fragments.append(("class:md-heading", heading.group(2)))
            elif _HR_RE.match(line):
                fragments.append(("class:md-hr", "─" * 20))
            else:
                quote = _QUOTE_RE.match(line)
                if quote:
                    fragments.extend(
                        [("class:md-quote", "▍ "), *render_inline(quote.group(1))]
                    )
                else:
                    list_match = _LIST_RE.match(line)
                    if list_match:
                        fragments.extend([("", "• "), *render_inline(list_match.group(1))])
                    else:
                        ordered_match = _ORDERED_LIST_RE.match(line)
                        if ordered_match:
                            fragments.extend(
                                [("", "· "), *render_inline(ordered_match.group(1))]
                            )
                        else:
                            fragments.extend(render_inline(line))
        if add_newline:
            fragments.append(("", "\n"))
    if table_rows is not None:
        fragments.extend(_render_table(table_rows))
    return fragments


def render_inline(text: str) -> StyleAndTextTuples:
    """把一行内的行内代码、链接、粗体和斜体标记转换为带样式的片段。"""

    fragments: StyleAndTextTuples = []
    for part in _INLINE_RE.split(text):
        if part.startswith("`") and part.endswith("`") and len(part) > 2:
            fragments.append(("class:md-code", part[1:-1]))
        elif part.startswith("[") and _LINK_RE.match(part):
            fragments.append(("class:md-link", _LINK_RE.match(part).group(1)))
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            fragments.append(("class:md-bold", part[2:-2]))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            fragments.append(("class:md-italic", part[1:-1]))
        elif part:
            fragments.append(("", _strip_unclosed_markers(part)))
    return fragments


def _strip_unclosed_markers(text: str) -> str:
    """移除未闭合的加粗（**）与行内代码（`）标记符号，只保留文字。

    单个星号 * 保留（避免误伤乘法等普通用法）；只有成对标记出现奇数个
    时才认定存在未闭合标记，去掉最后一个符号本身。
    """

    for marker in ("**", "`"):
        if text.count(marker) % 2 == 1:
            index = text.rfind(marker)
            text = text[:index] + text[index + len(marker) :]
    return text


def _render_table(rows: list[list[str]]) -> StyleAndTextTuples:
    """把表格行渲染为 │ 边框对齐的片段，分隔行跳过。"""

    data_rows = [row for row in rows if not _is_separator_row(row)]
    if not data_rows:
        return []
    # 计算每列宽度（CJK 按显示宽度）
    widths: list[int] = []
    for row in data_rows:
        for index, cell in enumerate(row):
            cell_width = wcswidth(cell)
            if index >= len(widths):
                widths.append(cell_width)
            else:
                widths[index] = max(widths[index], cell_width)
    fragments: StyleAndTextTuples = []
    for row_index, row in enumerate(data_rows):
        padded = [
            cell + " " * (widths[index] - wcswidth(cell))
            for index, cell in enumerate(row)
        ]
        line = "│ " + " │ ".join(padded) + " │"
        if row_index > 0:
            fragments.append(("", "\n"))
        if row_index == 0:
            fragments.append(("class:md-table-header", line))
        else:
            fragments.append(("", line))
    return fragments


def _is_separator_row(cells: list[str]) -> bool:
    """判断一行是否为表格分隔行（由 - : | 空格组成）。"""

    return bool(cells) and all(
        _TABLE_SEPARATOR_RE.fullmatch(cell) for cell in cells
    )
