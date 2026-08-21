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
    """扫描项目与全局 skill 目录，维护当前会话激活的 skill 集合。"""

    def __init__(
        self,
        workspace: Path,
        global_skills_dir: Path | None = None,
    ) -> None:
        """记录项目与全局 skill 根目录并准备空的激活集合。"""

        self._skills_dirs = [workspace / ".epsilon" / "skills"]
        global_dir = global_skills_dir or Path.home() / ".agents" / "skills"
        self._skills_dirs.append(global_dir)
        self._active: set[str] = set()

    def list_skills(self) -> list[Skill]:
        """扫描各根目录下 <name>/SKILL.md，项目目录优先且重名去重。"""

        skills: list[Skill] = []
        seen_names: set[str] = set()
        for skills_dir in self._skills_dirs:
            if not skills_dir.is_dir():
                continue
            for skill_dir in sorted(skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_path = skill_dir / "SKILL.md"
                if not skill_path.is_file():
                    continue
                try:
                    skill = _parse_skill(skill_path, skill_dir.name)
                except OSError:
                    continue
                if skill.name in seen_names:
                    continue
                seen_names.add(skill.name)
                skills.append(skill)
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
