"""实现 /skills 命令：查看可用与已激活的 skill。"""

from .registry import CommandContext, SlashCommand

_SOURCE_LABELS = {"project": "projects", "global": "global"}


async def skills_command(context: CommandContext) -> None:
    """列出全部 skill 及当前激活状态。"""

    skills = context.skill_manager.list_skills()
    if not skills:
        context.screen.add_entry("tool", "No skills found")
        return
    active = context.skill_manager.active_keys()
    lines = []
    for skill in skills:
        marker = "[on] " if (skill.name, skill.source) in active else "[off]"
        source_label = _SOURCE_LABELS.get(skill.source, skill.source)
        lines.append(f"{marker}{skill.name} ({source_label}) - {skill.description}")
    context.screen.add_entry("tool", "\n".join(lines))


skills_command_slash = SlashCommand(
    name="skills",
    description="List available and active skills",
    handler=skills_command,
)
