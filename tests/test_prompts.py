"""测试上下文提示词资源加载。"""

import pytest

from core.prompts import PromptLoadError, load_prompt


def test_load_prompt_reads_context_summary() -> None:
    assert "## Goal" in load_prompt("context_summary")


def test_load_prompt_caches_prompt_content() -> None:
    assert load_prompt("context_summary") is load_prompt("context_summary")


@pytest.mark.parametrize("name", ["", "../context_summary", "nested/name"])
def test_load_prompt_rejects_invalid_name(name: str) -> None:
    with pytest.raises(PromptLoadError):
        load_prompt(name)
