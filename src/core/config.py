"""加载并校验 864code 的运行配置。"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


class ConfigError(ValueError):
    """配置文件缺失或配置项不合法时抛出的异常。"""


@dataclass(frozen=True)
class Settings:
    """模型客户端运行所需的最小配置。"""

    base_url: str
    model_name: str
    api_key: str


def load_settings(env_path: Path | None = None) -> Settings:
    """从 .env 文件读取配置，并在启动前完成基础校验。"""

    config_path = env_path or _find_env_file()
    if not config_path.is_file():
        raise ConfigError(f"找不到配置文件: {config_path}")

    values = dotenv_values(config_path)
    base_url = _required_value(values.get("MODEL_BASE_URL"), "MODEL_BASE_URL")
    model_name = _required_value(values.get("MODEL_NAME"), "MODEL_NAME")
    api_key = _required_value(values.get("MODEL_API_KEY"), "MODEL_API_KEY")
    _validate_base_url(base_url)

    return Settings(
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
    )


def _required_value(value: str | None, name: str) -> str:
    """读取必填配置项，避免把空配置传给模型客户端。"""

    if value is None or not value.strip():
        raise ConfigError(f"缺少必填配置项: {name}")
    return value.strip()


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
