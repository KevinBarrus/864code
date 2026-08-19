"""限制工具返回给模型的文本大小。"""

MAX_TOOL_OUTPUT_BYTES = 16_000
MAX_TOOL_OUTPUT_LINES = 400
TRUNCATION_NOTICE = "\n… 工具输出已截断"


def limit_tool_output(
    content: str,
    *,
    max_bytes: int = MAX_TOOL_OUTPUT_BYTES,
    max_lines: int = MAX_TOOL_OUTPUT_LINES,
) -> str:
    """按 UTF-8 字节数和行数裁剪工具输出。"""

    notice_bytes = len(TRUNCATION_NOTICE.encode("utf-8"))
    if max_bytes <= notice_bytes or max_lines <= 0:
        raise ValueError("工具输出预算不足")

    content_budget = max_bytes - notice_bytes
    selected: list[str] = []
    used_bytes = 0
    truncated = False
    for line_number, line in enumerate(content.splitlines(keepends=True), start=1):
        if line_number > max_lines:
            truncated = True
            break
        encoded = line.encode("utf-8")
        if used_bytes + len(encoded) > content_budget:
            remaining = content_budget - used_bytes
            selected.append(encoded[:remaining].decode("utf-8", errors="ignore"))
            truncated = True
            break
        selected.append(line)
        used_bytes += len(encoded)
    if not truncated:
        return content
    return "".join(selected).rstrip() + TRUNCATION_NOTICE
