"""测试 skill 扫描、frontmatter 解析和激活状态。"""

from pathlib import Path

from core.skills import Skill, SkillManager


def _write_skill(root: Path, directory: str, frontmatter: str, body: str) -> None:
    """在指定 skill 根目录写入一个 skill 文件。"""

    skill_dir = root / directory
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\n{frontmatter}---\n{body}",
        encoding="utf-8",
    )


def _make_manager(tmp_path: Path) -> SkillManager:
    """创建隔离了全局目录的 SkillManager，避免读取真实主目录。"""

    return SkillManager(tmp_path, global_skills_dir=tmp_path / "global")


def test_list_skills_parses_frontmatter(tmp_path: Path) -> None:
    """测试项目 skill 扫描能解析 name 和 description。"""

    _write_skill(tmp_path / ".epsilon" / "skills", "git", "name: git-commit\ndescription: 生成提交信息\n", "提交正文")
    _write_skill(tmp_path / ".epsilon" / "skills", "api", "name: api-guide\ndescription: API 指南\n", "API 正文")

    skills = _make_manager(tmp_path).list_skills()

    assert [skill.name for skill in skills] == ["api-guide", "git-commit"]
    assert skills[0].description == "API 指南"
    assert skills[0].body == "API 正文"


def test_list_skills_returns_empty_without_skills_directory(tmp_path: Path) -> None:
    """测试没有任何 skill 根目录时返回空列表。"""

    assert _make_manager(tmp_path).list_skills() == []


def test_list_skills_falls_back_to_directory_name(tmp_path: Path) -> None:
    """测试缺少 frontmatter 时用目录名作为 skill 名。"""

    skill_dir = tmp_path / ".epsilon" / "skills" / "plain"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("无 frontmatter 的正文", encoding="utf-8")

    assert _make_manager(tmp_path).list_skills() == [
        Skill("plain", "", "无 frontmatter 的正文")
    ]


def test_list_skills_merges_project_and_global_roots(tmp_path: Path) -> None:
    """测试项目与全局 skill 根目录会被合并扫描。"""

    _write_skill(tmp_path / ".epsilon" / "skills", "git", "name: project-skill\ndescription: 项目 skill\n", "项目正文")
    _write_skill(tmp_path / "global", "lint", "name: global-skill\ndescription: 全局 skill\n", "全局正文")

    skills = _make_manager(tmp_path).list_skills()

    assert [skill.name for skill in skills] == ["project-skill", "global-skill"]


def test_list_skills_prefers_project_skill_on_name_conflict(tmp_path: Path) -> None:
    """测试项目与全局同名 skill 时优先保留项目版本。"""

    _write_skill(tmp_path / ".epsilon" / "skills", "git", "name: git-commit\ndescription: 项目版本\n", "项目正文")
    _write_skill(tmp_path / "global", "git", "name: git-commit\ndescription: 全局版本\n", "全局正文")

    skills = _make_manager(tmp_path).list_skills()

    assert len(skills) == 1
    assert skills[0].description == "项目版本"
    assert skills[0].body == "项目正文"


def test_activate_deactivate_and_set_active(tmp_path: Path) -> None:
    """测试激活集合的增删和整体替换。"""

    manager = _make_manager(tmp_path)

    manager.activate("a")
    manager.activate("b")
    assert manager.active_names() == {"a", "b"}

    manager.deactivate("a")
    assert manager.active_names() == {"b"}

    manager.set_active({"c"})
    assert manager.active_names() == {"c"}


def test_active_system_messages_includes_skill_body(tmp_path: Path) -> None:
    """测试激活的 skill 会转换为系统消息。"""

    _write_skill(tmp_path / ".epsilon" / "skills", "git", "name: git-commit\ndescription: x\n", "规范提交正文")

    manager = _make_manager(tmp_path)
    manager.activate("git-commit")

    messages = manager.active_system_messages()

    assert len(messages) == 1
    assert messages[0].role == "system"
    assert "git-commit" in messages[0].content
    assert "规范提交正文" in messages[0].content
