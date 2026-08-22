"""/background-image 命令测试。"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.commands import (
    CommandContext,
    background_image_command_slash,
    model_command_slash,
)
from core.commands.background_image import (
    _apply_background,
    _read_background,
    _settings_path,
)


class _Screen:
    """记录 add_entry 调用与选择器输入的假界面。"""

    def __init__(self, choices: list[str | None]) -> None:
        self.entries: list[tuple[str, str]] = []
        self.choices = list(choices)
        self.text_inputs: list[str | None] = []
        self.application = SimpleNamespace(
            exit=lambda: None, invalidate=lambda: None
        )

    def add_entry(self, role: str, content: str, style: str = "") -> int:
        self.entries.append((role, content))
        return len(self.entries) - 1

    async def request_choice_picker(
        self, items, title, extra_options=None
    ) -> str | None:
        return self.choices.pop(0) if self.choices else None

    async def request_text_input(self, title, is_password=False) -> str | None:
        return self.text_inputs.pop(0) if self.text_inputs else None


def _context(screen: _Screen, project_dir: Path) -> CommandContext:
    return CommandContext(
        screen=screen,
        session=SimpleNamespace(),
        skill_manager=SimpleNamespace(),
        context_manager=SimpleNamespace(),
        client_holder=SimpleNamespace(
            client=object(),
            settings=SimpleNamespace(
                model_name="m", base_url="https://x", api_key="k"
            ),
        ),
        agent_loop=SimpleNamespace(thinking_level="high"),
        project_dir=project_dir,
        tool_manager=None,
    )


def _write_settings(path: Path, background: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"model": {"base_url": "u", "api_key": "k", "model_name": "m"}, "background": background}),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_background_add_saves_and_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """测试添加背景图：校验格式、保存配置并尝试应用。"""

    image = tmp_path / "wall.png"
    image.write_bytes(b"png")
    screen = _Screen([None])  # 主菜单取消后不再继续
    context = _context(screen, tmp_path)
    path = _settings_path(tmp_path)

    from core.commands import background_image as module

    async def fake_write(path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(module, "write_settings_atomically", fake_write)
    monkeypatch.setattr(module, "_apply_background", lambda p, t: f"applied: {p}")

    # 直接走添加流程：先选 add options，再输入名字和路径
    screen.choices = ["add options"]
    screen.text_inputs = ["wall", str(image)]

    await background_image_command_slash.handler(context)

    stored = _read_background(path)
    assert stored["current"] == "wall"
    assert stored["images"]["wall"] == str(image)
    assert any("applied" in content for _, content in screen.entries)


@pytest.mark.asyncio
async def test_background_rejects_bad_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """测试不支持的图片格式被拒绝。"""

    bad = tmp_path / "wall.txt"
    bad.write_text("text", encoding="utf-8")
    screen = _Screen([])
    screen.choices = ["add options"]
    screen.text_inputs = ["wall", str(bad)]
    context = _context(screen, tmp_path)

    await background_image_command_slash.handler(context)

    assert any("Unsupported image format" in content for _, content in screen.entries)


@pytest.mark.asyncio
async def test_background_transparency_validates_two_decimals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """测试透明度必须为两位小数且在 0-1 范围内。"""

    screen = _Screen([])
    screen.choices = ["transparency"]
    screen.text_inputs = ["0.5"]  # 只有一位小数
    context = _context(screen, tmp_path)

    await background_image_command_slash.handler(context)

    assert any(
        "two decimals" in content for _, content in screen.entries
    )


def test_apply_background_unsupported_without_iterm(monkeypatch) -> None:
    """测试非 iTerm2 终端返回不支持提示。"""

    monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
    result = _apply_background("/tmp/a.png", 0.5)

    assert "unsupported in this terminal" in result


def test_apply_background_sends_sequence(monkeypatch, capsys) -> None:
    """测试 iTerm2 下发送 OSC 1337 背景图序列。"""

    monkeypatch.setenv("ITERM_SESSION_ID", "test")
    result = _apply_background("/tmp/a.png", 0.5)
    captured = capsys.readouterr()

    assert "applied" in result
    assert "\x1b]1337;SetBackgroundImage=file:///tmp/a.png\x07" in captured.out


@pytest.mark.asyncio
async def test_model_save_keeps_background_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """测试 /model 保存后 background 配置仍然保留。"""

    settings_path = tmp_path / ".epsilon" / "settings.json"
    _write_settings(
        settings_path,
        {"current": "wall", "transparency": 0.5, "images": {"wall": "/tmp/a.png"}},
    )
    screen = _Screen([None])
    screen.choices = [None]  # 选择器直接取消，触发保存分支前的返回
    context = _context(screen, tmp_path)

    # 直接调用保存辅助函数验证合并行为
    from core.commands.model import _save_model_config

    await _save_model_config(
        settings_path,
        {"base_url": "u2", "api_key": "k2", "model_name": "m2"},
    )

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["model"]["model_name"] == "m2"
    assert data["background"]["current"] == "wall"
