"""epsilon 的程序启动入口"""

import asyncio
import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from .config import ConfigError, load_settings
from .context import ContextBudget
from .balance import UnavailableBalanceProvider
from .openai_client import OpenAICompatibleClient
from .session_picker import SessionPicker
from .session_store import SessionStore
from .session_store import SessionStoreError
from .status import create_status_info
from .tools import StdioMcpProvider
from .ui import run_chat


logger = logging.getLogger(__name__)


async def run(session_id: str | None = None, resume: bool = False) -> None:
    """加载配置、创建模型客户端并启动终端界面"""

    workspace = Path.cwd().resolve()
    if resume and session_id is None:
        summaries = SessionStore(workspace).list_sessions()
        session_id = await SessionPicker(summaries).pick()
        if session_id is None:
            print("没有选择会话，已退出")
            return

    settings = load_settings()
    client = OpenAICompatibleClient(settings)
    mcp_provider = (
        StdioMcpProvider(
            (settings.mcp_stdio.command, *settings.mcp_stdio.arguments),
            settings.mcp_stdio.provider_id,
            cwd=workspace,
        )
        if settings.mcp_stdio is not None
        else None
    )
    balance = await UnavailableBalanceProvider().get_balance()
    status = create_status_info(settings.model_name, balance)
    await run_chat(
        client,
        status,
        workspace,
        session_id,
        ContextBudget(
            settings.context_window,
            settings.reserve_tokens,
            settings.keep_recent_tokens,
        ),
        mcp_provider=mcp_provider,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """处理启动阶段的错误并返回进程退出码"""

    parser = argparse.ArgumentParser(description="启动 epsilon")
    subparsers = parser.add_subparsers(dest="command")
    resume_parser = subparsers.add_parser("resume", help="恢复已有会话")
    resume_parser.add_argument("session_id", nargs="?", help="要恢复的会话 ID")
    args = parser.parse_args(argv)

    try:
        asyncio.run(
            run(
                getattr(args, "session_id", None),
                resume=args.command == "resume",
            )
        )
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except SessionStoreError as exc:
        print(f"会话错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已退出。")
    except Exception:
        logger.debug("启动过程发生未分类异常", exc_info=True)
        print("运行错误：发生未预期错误，请重试或查看调试日志", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
