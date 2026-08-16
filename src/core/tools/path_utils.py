"""提供本地工具使用的工作区路径校验。"""

from pathlib import Path


class WorkspacePathError(ValueError):
    """工具路径不在工作区内时抛出的异常。"""


def resolve_workspace_path(workspace: Path, value: str) -> Path:
    """解析路径并拒绝访问工作区之外的位置。"""

    workspace = workspace.resolve()
    path = (workspace / value).resolve()
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise WorkspacePathError("路径必须位于当前工作区内") from exc
    return path
