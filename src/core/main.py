"""864code 的程序启动入口。"""

import asyncio
import sys

from .config import ConfigError, load_settings
from .balance import UnavailableBalanceProvider
from .openai_client import OpenAICompatibleClient
from .status import create_status_info
from .ui import run_chat


async def run() -> None:
    """加载配置、创建模型客户端并启动终端界面。"""

    settings = load_settings()
    client = OpenAICompatibleClient(settings)
    balance = await UnavailableBalanceProvider().get_balance()
    status = create_status_info(settings.model_name, balance)
    await run_chat(client, status)


def main() -> int:
    """处理启动阶段的错误并返回进程退出码。"""

    try:
        asyncio.run(run())
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已退出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
