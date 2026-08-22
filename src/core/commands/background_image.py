"""实现 /background-image 命令：查看、添加与切换终端背景图配置。

背景图配置保存在 settings.json 顶层的 background 键（images 名称到路径、
current 当前项、transparency 透明度），应用时向支持 OSC 1337 的终端
（iTerm2）发送 SetBackgroundImage 序列。
"""

import json
import os
import re
import sys
from pathlib import Path

from ..setup import write_settings_atomically
from .registry import CommandContext, SlashCommand

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_CURRENT_OPTION = "current options"
_ADD_OPTION = "add options"
_TRANSPARENCY_OPTION = "transparency"
_CHOICE_HINTS = "↑/↓ move, Enter confirm, Esc cancel"
_TRANSPARENCY_RE = re.compile(r"^\d+\.\d{2}$")


def _settings_path(project_dir: Path) -> Path:
    """返回背景图配置所在的 settings.json 路径。"""

    return project_dir / ".epsilon" / "settings.json"


def _read_background(path: Path) -> dict:
    """读取 settings.json 中的 background 配置，缺失或损坏时返回默认值。"""

    default = {"current": "", "transparency": 0.5, "images": {}}
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default
    background = data.get("background")
    if not isinstance(background, dict):
        return default
    images = background.get("images")
    return {
        "current": background.get("current", ""),
        "transparency": background.get("transparency", 0.5),
        "images": images if isinstance(images, dict) else {},
    }


async def _write_background(path: Path, background: dict) -> None:
    """把 background 合并写回 settings.json，保留 model 等其他字段。"""

    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data["background"] = background
    await write_settings_atomically(path, data)


def _apply_background(path: str, transparency: float) -> str:
    """向终端发送背景图序列，返回应用结果提示。"""

    if os.environ.get("ITERM_SESSION_ID") is None:
        return f"(unsupported in this terminal) {path}"
    sys.stdout.write(f"\x1b]1337;SetBackgroundImage=file://{path}\x07")
    sys.stdout.flush()
    return f"applied: {path} (transparency {transparency})"


async def background_image_command(context: CommandContext) -> None:
    """展示背景图管理菜单并处理查看、添加与透明度调整。"""

    path = _settings_path(context.project_dir)
    background = _read_background(path)
    action = await context.screen.request_choice_picker(
        [_CURRENT_OPTION, _ADD_OPTION, _TRANSPARENCY_OPTION],
        f"Background image ({_CHOICE_HINTS})",
    )
    if action is None:
        return
    if action == _CURRENT_OPTION:
        await _manage_current(context, path, background)
    elif action == _ADD_OPTION:
        await _add_image(context, path, background)
    else:
        await _set_transparency(context, path, background)


async def _manage_current(context: CommandContext, path: Path, background: dict) -> None:
    """列出已添加的背景图，选择一项设为当前并应用。"""

    images = background["images"]
    if not images:
        context.screen.add_entry("tool", "No background images added, use add options")
        return
    current = background["current"]
    items = []
    current_index = 0
    for index, (name, image_path) in enumerate(images.items()):
        marker = " (current)" if name == current else ""
        items.append(f"{name} - {image_path}{marker}")
        if name == current:
            current_index = index
    choice = await context.screen.request_choice_picker(
        items,
        f"Current background (pink marks active, {_CHOICE_HINTS})",
    )
    if choice is None:
        return
    name = choice.split(" - ", 1)[0]
    background["current"] = name
    await _write_background(path, background)
    context.screen.add_entry(
        "tool", _apply_background(images[name], background["transparency"])
    )


async def _add_image(context: CommandContext, path: Path, background: dict) -> None:
    """输入配置名与图片路径，校验后添加并设为当前。"""

    name = await context.screen.request_text_input("Image config name")
    if not name:
        return
    image_path_text = await context.screen.request_text_input(
        f"Image path for {name}"
    )
    if not image_path_text:
        return
    image_path = Path(image_path_text).expanduser()
    if not image_path.is_file():
        context.screen.add_entry("tool", f"File not found: {image_path}")
        return
    if image_path.suffix.lower() not in _IMAGE_EXTENSIONS:
        context.screen.add_entry(
            "tool", f"Unsupported image format: {image_path.suffix}"
        )
        return
    background["images"][name] = str(image_path)
    background["current"] = name
    await _write_background(path, background)
    context.screen.add_entry(
        "tool", _apply_background(str(image_path), background["transparency"])
    )


async def _set_transparency(
    context: CommandContext, path: Path, background: dict
) -> None:
    """输入两位小数透明度（0.00-1.00，越小越透明）并保存。"""

    value = await context.screen.request_text_input(
        "Transparency (0.00-1.00, smaller is more transparent)"
    )
    if not value:
        return
    if not _TRANSPARENCY_RE.fullmatch(value):
        context.screen.add_entry("tool", "Transparency must be two decimals (e.g. 0.50)")
        return
    transparency = float(value)
    if not 0.0 <= transparency <= 1.0:
        context.screen.add_entry("tool", "Transparency must be between 0.00 and 1.00")
        return
    background["transparency"] = transparency
    await _write_background(path, background)
    current = background["current"]
    if current:
        context.screen.add_entry(
            "tool", _apply_background(background["images"][current], transparency)
        )
    else:
        context.screen.add_entry("tool", f"Transparency saved: {transparency}")


background_image_command_slash = SlashCommand(
    name="background-image",
    description="Manage the terminal background image",
    handler=background_image_command,
)
