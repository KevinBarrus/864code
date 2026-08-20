"""测试 slash command 注册与分发。"""

import pytest

from core.commands import CommandRegistrationError, CommandRegistry, SlashCommand


class _DummyContext:
    """测试用最小命令上下文。"""


@pytest.mark.asyncio
async def test_registry_registers_finds_and_dispatches() -> None:
    """测试注册表能注册、查找并分发命令。"""

    registry = CommandRegistry()
    calls: list[str] = []

    async def handler(context) -> None:
        calls.append("handled")

    registry.register(SlashCommand("ping", "测试命令", handler))

    assert registry.get("ping") is not None
    assert await registry.dispatch("/ping", _DummyContext()) is True
    assert calls == ["handled"]


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_command_name() -> None:
    """测试重复命令名会被拒绝注册。"""

    registry = CommandRegistry()

    async def handler(context) -> None:
        return None

    registry.register(SlashCommand("ping", "首次", handler))
    with pytest.raises(CommandRegistrationError, match="ping"):
        registry.register(SlashCommand("ping", "重复", handler))


@pytest.mark.asyncio
async def test_dispatch_ignores_non_command_and_unknown_command() -> None:
    """测试非命令输入和未知命令不会触发处理器。"""

    registry = CommandRegistry()
    calls: list[str] = []

    async def handler(context) -> None:
        calls.append("handled")

    registry.register(SlashCommand("ping", "测试", handler))

    assert await registry.dispatch("普通消息", _DummyContext()) is False
    assert await registry.dispatch("/unknown", _DummyContext()) is False
    assert await registry.dispatch("/", _DummyContext()) is False
    assert calls == []


def test_registry_lists_registered_commands() -> None:
    """测试注册表返回全部命令。"""

    registry = CommandRegistry()

    async def handler(context) -> None:
        return None

    registry.register(SlashCommand("a", "A", handler))
    registry.register(SlashCommand("b", "B", handler))

    assert [command.name for command in registry.list()] == ["a", "b"]
