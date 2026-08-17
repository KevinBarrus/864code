from pathlib import Path

import pytest

from core.config import ConfigError, load_settings


def _write_env(tmp_path: Path, content: str) -> Path:
    """在临时目录写入测试用的 .env 文件。"""

    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


def test_load_settings_reads_required_values(tmp_path: Path) -> None:
    """测试配置加载器能读取三个必填配置项。"""

    env_path = _write_env(
        tmp_path,
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n",
    )

    settings = load_settings(env_path)

    assert settings.base_url == "https://example.com/v1"
    assert settings.model_name == "test-model"
    assert settings.api_key == "test-key"


def test_load_settings_reads_optional_context_budget(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n"
        "MODEL_CONTEXT_WINDOW=50000\n"
        "MODEL_RESERVE_TOKENS=8000\n"
        "MODEL_KEEP_RECENT_TOKENS=12000\n",
        encoding="utf-8",
    )

    settings = load_settings(env_path)

    assert settings.context_window == 50000
    assert settings.reserve_tokens == 8000
    assert settings.keep_recent_tokens == 12000


def test_load_settings_rejects_missing_value(tmp_path: Path) -> None:
    """测试缺少 API Key 时会抛出明确的配置异常。"""

    env_path = _write_env(
        tmp_path,
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n",
    )

    with pytest.raises(ConfigError, match="MODEL_API_KEY"):
        load_settings(env_path)


def test_load_settings_rejects_invalid_base_url(tmp_path: Path) -> None:
    """测试模型服务地址格式不正确时会抛出配置异常。"""

    env_path = _write_env(
        tmp_path,
        "MODEL_BASE_URL=example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n",
    )

    with pytest.raises(ConfigError, match="MODEL_BASE_URL"):
        load_settings(env_path)


def test_load_settings_finds_env_in_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试从 src 等子目录启动时能找到项目根目录的 .env。"""

    _write_env(
        tmp_path,
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n",
    )
    source_directory = tmp_path / "src"
    source_directory.mkdir()
    monkeypatch.chdir(source_directory)

    settings = load_settings()

    assert settings.model_name == "test-model"
