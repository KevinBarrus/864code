"""实现 skill 扫描、frontmatter 解析和激活状态管理。"""

from dataclasses import dataclass
from pathlib import Path

from ..model import Message


@dataclass(frozen=True)
class Skill:
    """一个可激活的 skill，包含元数据、正文和来源。"""

    name: str
    description: str
    body: str
    source: str


class SkillManager:
    """扫描项目与全局 skill 目录，维护当前会话激活的 skill 集合。"""

    def __init__(
        self,
        workspace: Path,
        global_skills_dir: Path | None = None,
    ) -> None:
        """记录项目与全局 skill 根目录并准备空的激活集合。"""

        self._skills_roots: list[tuple[Path, str]] = [
            (workspace / ".epsilon" / "skills", "project")
        ]
        global_dir = global_skills_dir or Path.home() / ".agents" / "skills"
        self._skills_roots.append((global_dir, "global"))
        self._active: set[tuple[str, str]] = set()

    def list_skills(self) -> list[Skill]:
        """扫描各根目录下 <name>/SKILL.md，重名 skill 全部保留并标注来源。"""

        skills: list[Skill] = []
        for skills_dir, source in self._skills_roots:
            if not skills_dir.is_dir():
                continue
            for skill_dir in sorted(skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_path = skill_dir / "SKILL.md"
                if not skill_path.is_file():
                    continue
                try:
                    skills.append(_parse_skill(skill_path, skill_dir.name, source))
                except OSError:
                    continue
        return skills

    def activate(self, name: str, source: str) -> None:
        """按名称与来源激活一个 skill。"""

        self._active.add((name, source))

    def deactivate(self, name: str, source: str) -> None:
        """按名称与来源取消激活一个 skill。"""

        self._active.discard((name, source))

    def set_active(self, keys: set[tuple[str, str]]) -> None:
        """用指定的 (name, source) 集合替换当前激活集合。"""

        self._active = set(keys)

    def active_keys(self) -> set[tuple[str, str]]:
        """返回当前激活的 (name, source) 集合副本。"""

        return set(self._active)

    def active_system_messages(self) -> list[Message]:
        """将激活的 skill 正文转换为系统消息，并标注来源。"""

        by_key = {(skill.name, skill.source): skill for skill in self.list_skills()}
        messages: list[Message] = []
        for name, source in sorted(self._active):
            skill = by_key.get((name, source))
            if skill is None:
                continue
            messages.append(
                Message(
                    role="system",
                    content=f"Active skill: {name} (source: {source})\n\n{skill.body}",
                )
            )
        return messages


def _parse_skill(path: Path, fallback_name: str, source: str) -> Skill:
    """解析 SKILL.md 的 frontmatter 和正文，无 frontmatter 时使用目录名。"""

    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body = parts[2].strip()
            name = _frontmatter_value(frontmatter, "name") or fallback_name
            description = _frontmatter_value(frontmatter, "description") or ""
            return Skill(name, description, body, source)
    return Skill(fallback_name, "", text.strip(), source)


def _frontmatter_value(frontmatter: str, key: str) -> str:
    """从 frontmatter 文本中提取指定键的值。"""

    for line in frontmatter.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""
