"""实现 /start-skill 命令。"""

from .registry import CommandContext, SlashCommand


async def start_skill(context: CommandContext) -> None:
    """展示可用 skill 并让用户勾选激活。"""

    skills = context.skill_manager.list_skills()
    if not skills:
        context.screen.add_entry("tool", "没有可用的 skill")
        return
    selected = await context.screen.request_skill_picker(
        [(skill.name, skill.description) for skill in skills],
        context.skill_manager.active_names(),
    )
    if selected is None:
        return
    _apply_active_skills(context, selected)
    if selected:
        context.screen.set_status_message(
            f"已激活 skill：{', '.join(sorted(selected))}"
        )


def _apply_active_skills(context: CommandContext, selected: set[str]) -> None:
    """把用户勾选的集合写回 skill 管理器并刷新上下文注入。"""

    context.skill_manager.set_active(selected)
    context.context_manager.set_extra_system_messages(
        context.skill_manager.active_system_messages()
    )


start_skill_command = SlashCommand(
    name="start-skill",
    description="选择并激活要生效的 skill",
    handler=start_skill,
)
