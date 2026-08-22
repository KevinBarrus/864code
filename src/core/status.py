"""定义状态栏展示所需的数据。"""

from dataclasses import dataclass
from pathlib import Path


def format_cwd_for_footer(cwd: str, home: str | None = None) -> str:
    """把 home 目录缩写为 ~（对齐 Pi formatCwdForFooter），不在 home 下时原样返回。"""

    if not home:
        return cwd
    try:
        relative = Path(cwd).resolve().relative_to(Path(home).resolve())
    except ValueError:
        return cwd
    if str(relative) == ".":
        return "~"
    return f"~/{relative}"


@dataclass(frozen=True)
class StatusInfo:
    """状态栏中的模型、余额和当前工作目录。"""

    model_name: str
    balance: str
    working_directory: Path


def create_status_info(
    model_name: str,
    balance: str,
    working_directory: Path | None = None,
) -> StatusInfo:
    """创建状态栏数据，默认使用当前工作目录。"""

    return StatusInfo(
        model_name=model_name,
        balance=balance,
        working_directory=(working_directory or Path.cwd()).resolve(),
    )
