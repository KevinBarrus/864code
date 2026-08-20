"""实现 skill 扫描、frontmatter 解析和激活状态管理。"""

from dataclasses import dataclass
from pathlib import Path

from ..model import Message


@dataclass(frozen=True)
class Skill:
    """一个可激活的 skill，包含元数据和正文。"""

    name: str
    description: str
    body: str


class SkillManager:
    """扫描项目 skills 目录，维护当前会话激活的 skill 集合。"""

    def __init__(self, workspace: Path) -> None:
        """记录工作区并准备空的激活集合。"""

        self._skills_dir = workspace / "skills"
        self._active: set[str] = set()

    def list_skills(self) -> list[Skill]:
        """扫描 skills/<name>/SKILL.md，返回全部可用 skill。"""

        if not self._skills_dir.is_dir():
            return []
        skills: list[Skill] = []
        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_path = skill_dir / "SKILL.md"
            if not skill_path.is_file():
                continue
            try:
                skills.append(_parse_skill(skill_path, skill_dir.name))
            except OSError:
                continue
        return skills

    def activate(self, name: str) -> None:
        """激活一个 skill。"""

        self._active.add(name)

    def deactivate(self, name: str) -> None:
        """取消激活一个 skill。"""

        self._active.discard(name)

    def set_active(self, names: set[str]) -> None:
        """用指定的集合替换当前激活集合。"""

        self._active = set(names)

    def active_names(self) -> set[str]:
        """返回当前激活的 skill 名称副本。"""

        return set(self._active)

    def active_system_messages(self) -> list[Message]:
        """将激活的 skill 正文转换为系统消息，供上下文注入。"""

        by_name = {skill.name: skill for skill in self.list_skills()}
        messages: list[Message] = []
        for name in sorted(self._active):
            skill = by_name.get(name)
            if skill is None:
                continue
            messages.append(
                Message(
                    role="system",
                    content=f"当前激活的 skill：{name}\n\n{skill.body}",
                )
            )
        return messages


def _parse_skill(path: Path, fallback_name: str) -> Skill:
    """解析 SKILL.md 的 frontmatter 和正文，无 frontmatter 时使用目录名。"""

    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body = parts[2].strip()
            name = _frontmatter_value(frontmatter, "name") or fallback_name
            description = _frontmatter_value(frontmatter, "description") or ""
            return Skill(name, description, body)
    return Skill(fallback_name, "", text.strip())


def _frontmatter_value(frontmatter: str, key: str) -> str:
    """从 frontmatter 文本中提取指定键的值。"""

    for line in frontmatter.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""
