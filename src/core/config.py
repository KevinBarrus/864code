"""加载并校验 864code 的运行配置。"""

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


class ConfigError(ValueError):
    """配置文件缺失或配置项不合法时抛出的异常。"""


@dataclass(frozen=True)
class McpStdioSettings:
    """描述一个可选 stdio MCP Provider 的启动配置。"""

    command: str
    arguments: tuple[str, ...]
    provider_id: str


@dataclass(frozen=True)
class Settings:
    """模型客户端运行所需的最小配置。"""

    base_url: str
    model_name: str
    api_key: str
    context_window: int = 100_000
    reserve_tokens: int = 16_000
    keep_recent_tokens: int = 20_000
    request_timeout_seconds: float = 120.0
    mcp_stdio: McpStdioSettings | None = None


def load_settings(env_path: Path | None = None) -> Settings:
    """从 .env 文件读取配置，并在启动前完成基础校验。"""

    config_path = env_path or _find_env_file()
    if not config_path.is_file():
        raise ConfigError(f"找不到配置文件: {config_path}")

    values = dotenv_values(config_path)
    base_url = _required_value(values.get("MODEL_BASE_URL"), "MODEL_BASE_URL")
    model_name = _required_value(values.get("MODEL_NAME"), "MODEL_NAME")
    api_key = _required_value(values.get("MODEL_API_KEY"), "MODEL_API_KEY")
    context_window = _optional_int(values.get("MODEL_CONTEXT_WINDOW"), 100_000)
    reserve_tokens = _optional_int(values.get("MODEL_RESERVE_TOKENS"), 16_000)
    keep_recent_tokens = _optional_int(values.get("MODEL_KEEP_RECENT_TOKENS"), 20_000)
    request_timeout_seconds = _optional_float(
        values.get("MODEL_REQUEST_TIMEOUT_SECONDS"),
        120.0,
        "MODEL_REQUEST_TIMEOUT_SECONDS",
    )
    mcp_stdio = _optional_mcp_stdio_settings(values)
    if context_window <= 0:
        raise ConfigError("MODEL_CONTEXT_WINDOW 必须大于 0")
    if reserve_tokens < 0 or reserve_tokens >= context_window:
        raise ConfigError("MODEL_RESERVE_TOKENS 必须小于 MODEL_CONTEXT_WINDOW")
    if keep_recent_tokens <= 0:
        raise ConfigError("MODEL_KEEP_RECENT_TOKENS 必须大于 0")
    if request_timeout_seconds <= 0:
        raise ConfigError("MODEL_REQUEST_TIMEOUT_SECONDS 必须大于 0")
    _validate_base_url(base_url)

    return Settings(
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        context_window=context_window,
        reserve_tokens=reserve_tokens,
        keep_recent_tokens=keep_recent_tokens,
        request_timeout_seconds=request_timeout_seconds,
        mcp_stdio=mcp_stdio,
    )


def _required_value(value: str | None, name: str) -> str:
    """读取必填配置项，避免把空配置传给模型客户端。"""

    if value is None or not value.strip():
        raise ConfigError(f"缺少必填配置项: {name}")
    return value.strip()


def _optional_int(value: str | None, default: int) -> int:
    """读取可选整数配置，未设置时使用默认值。"""

    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ConfigError("上下文预算配置必须是整数") from exc


def _optional_float(value: str | None, default: float, name: str) -> float:
    """读取可选小数配置，未设置时使用默认值。"""

    if value is None or not value.strip():
        return default
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是数字") from exc


def _optional_mcp_stdio_settings(values: dict[str, str | None]) -> McpStdioSettings | None:
    """读取可选单个 stdio MCP 配置，并校验参数 JSON 数组。"""

    command = values.get("MCP_STDIO_COMMAND")
    arguments = values.get("MCP_STDIO_ARGS")
    provider_id = values.get("MCP_STDIO_PROVIDER_ID")
    if not any(value is not None and value.strip() for value in (command, arguments, provider_id)):
        return None

    raw_arguments = arguments.strip() if arguments else "[]"
    try:
        parsed_arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ConfigError("MCP_STDIO_ARGS 必须是 JSON 字符串数组") from exc
    if not isinstance(parsed_arguments, list) or not all(
        isinstance(argument, str) for argument in parsed_arguments
    ):
        raise ConfigError("MCP_STDIO_ARGS 必须是 JSON 字符串数组")
    return McpStdioSettings(
        command=_required_value(command, "MCP_STDIO_COMMAND"),
        arguments=tuple(parsed_arguments),
        provider_id=_required_value(provider_id, "MCP_STDIO_PROVIDER_ID"),
    )


def _find_env_file() -> Path:
    """从当前目录开始向父目录查找 .env 文件。"""

    current_directory = Path.cwd().resolve()
    for directory in (current_directory, *current_directory.parents):
        env_path = directory / ".env"
        if env_path.is_file():
            return env_path
    return current_directory / ".env"


def _validate_base_url(base_url: str) -> None:
    """确保模型服务地址使用可识别的 HTTP 协议。"""

    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ConfigError("MODEL_BASE_URL 必须是有效的 http 或 https 地址")
