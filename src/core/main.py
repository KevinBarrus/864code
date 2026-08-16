"""864code 的程序启动入口"""

import asyncio
import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .config import ConfigError, load_settings
from .balance import UnavailableBalanceProvider
from .openai_client import OpenAICompatibleClient
from .session_store import SessionStoreError
from .status import create_status_info
from .ui import run_chat


async def run(session_id: str | None = None) -> None:
    """加载配置、创建模型客户端并启动终端界面"""

    workspace = Path.cwd().resolve()
    settings = load_settings()
    client = OpenAICompatibleClient(settings)
    balance = await UnavailableBalanceProvider().get_balance()
    status = create_status_info(settings.model_name, balance)
    await run_chat(client, status, workspace, session_id)


def main(argv: Sequence[str] | None = None) -> int:
    """处理启动阶段的错误并返回进程退出码"""

    parser = argparse.ArgumentParser(description="启动 864code")
    parser.add_argument("--session-id", help="恢复指定的会话")
    args = parser.parse_args(argv)

    try:
        asyncio.run(run(args.session_id))
    except (ConfigError, SessionStoreError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已退出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
