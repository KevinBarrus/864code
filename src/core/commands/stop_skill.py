"""实现 /stop-skill 命令。"""

from .registry import CommandContext, SlashCommand
from .start_skill import _apply_active_skills


async def stop_skill(context: CommandContext) -> None:
    """展示已激活 skill 并让用户取消。"""

    active = context.skill_manager.active_names()
    if not active:
        context.screen.add_entry("tool", "当前没有激活的 skill")
        return
    active_skills = [
        (skill.name, skill.description)
        for skill in context.skill_manager.list_skills()
        if skill.name in active
    ]
    selected = await context.screen.request_skill_picker(active_skills, active)
    if selected is None:
        return
    removed = sorted(active - selected)
    _apply_active_skills(context, selected)
    if removed:
        context.screen.set_status_message(f"已停止 skill：{', '.join(removed)}")


stop_skill_command = SlashCommand(
    name="stop-skill",
    description="取消已激活的 skill",
    handler=stop_skill,
)
