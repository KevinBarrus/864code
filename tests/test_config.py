from pathlib import Path

import pytest

from core.config import ConfigError, McpStdioSettings, Settings, load_settings


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


def test_load_settings_reads_request_timeout(tmp_path: Path) -> None:
    """测试旧请求超时会作为两类超时的兼容默认值。"""

    env_path = _write_env(
        tmp_path,
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n"
        "MODEL_REQUEST_TIMEOUT_SECONDS=45.5\n",
    )

    settings = load_settings(env_path)

    assert settings.request_timeout_seconds == 45.5
    assert settings.first_byte_timeout_seconds == 45.5
    assert settings.stream_idle_timeout_seconds == 45.5


def test_settings_direct_construction_uses_legacy_timeout_as_fallback() -> None:
    """测试直接构造配置也会统一超时回退。"""

    settings = Settings(
        base_url="https://example.com/v1",
        model_name="test-model",
        api_key="test-key",
        request_timeout_seconds=0.01,
    )

    assert settings.first_byte_timeout_seconds == 0.01
    assert settings.stream_idle_timeout_seconds == 0.01


def test_settings_rejects_invalid_direct_timeout() -> None:
    """测试直接构造配置会校验超时值。"""

    with pytest.raises(ConfigError, match="MODEL_STREAM_IDLE_TIMEOUT_SECONDS"):
        Settings(
            base_url="https://example.com/v1",
            model_name="test-model",
            api_key="test-key",
            stream_idle_timeout_seconds=0,
        )


def test_load_settings_reads_separate_stream_timeouts(tmp_path: Path) -> None:
    """测试首包和流式空闲超时可以独立配置。"""

    env_path = _write_env(
        tmp_path,
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n"
        "MODEL_REQUEST_TIMEOUT_SECONDS=45.5\n"
        "MODEL_FIRST_BYTE_TIMEOUT_SECONDS=12\n"
        "MODEL_STREAM_IDLE_TIMEOUT_SECONDS=34\n",
    )

    settings = load_settings(env_path)

    assert settings.first_byte_timeout_seconds == 12
    assert settings.stream_idle_timeout_seconds == 34


def test_load_settings_reads_optional_stdio_mcp_provider(tmp_path: Path) -> None:
    """测试可选 stdio MCP Provider 配置会被完整读取。"""

    env_path = _write_env(
        tmp_path,
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n"
        "MCP_STDIO_COMMAND=node\n"
        'MCP_STDIO_ARGS=["server.js","--readonly"]\n'
        "MCP_STDIO_PROVIDER_ID=demo\n",
    )

    assert load_settings(env_path).mcp_stdio == McpStdioSettings(
        command="node",
        arguments=("server.js", "--readonly"),
        provider_id="demo",
    )


def test_load_settings_rejects_invalid_stdio_mcp_arguments(tmp_path: Path) -> None:
    """测试 MCP 参数必须是 JSON 字符串数组。"""

    env_path = _write_env(
        tmp_path,
        "MODEL_BASE_URL=https://example.com/v1\n"
        "MODEL_NAME=test-model\n"
        "MODEL_API_KEY=test-key\n"
        "MCP_STDIO_COMMAND=node\n"
        "MCP_STDIO_ARGS=--server\n"
        "MCP_STDIO_PROVIDER_ID=demo\n",
    )

    with pytest.raises(ConfigError, match="MCP_STDIO_ARGS"):
        load_settings(env_path)


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
