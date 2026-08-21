"""epsilon 的程序启动入口"""

import asyncio
import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from .config import ConfigError, default_user_config_path, load_settings
from .context import ContextBudget
from .balance import create_balance_provider
from .openai_client import OpenAICompatibleClient
from .session_picker import SessionPicker
from .session_store import SessionStore
from .session_store import SessionStoreError
from .setup import run_setup_guide
from .status import create_status_info
from .tools import StdioMcpProvider
from .ui import run_chat


logger = logging.getLogger(__name__)


async def run(
    session_id: str | None = None,
    resume: bool = False,
    config_path: Path | None = None,
) -> None:
    """加载配置、创建模型客户端并启动终端界面"""

    workspace = Path.cwd().resolve()
    if resume and session_id is None:
        summaries = SessionStore(workspace).list_sessions()
        session_id = await SessionPicker(summaries).pick()
        if session_id is None:
            print("No session selected, exiting")
            return

    if config_path is None and not default_user_config_path().is_file():
        completed = await run_setup_guide(default_user_config_path())
        if not completed:
            print("Setup incomplete, exiting")
            return
    settings = load_settings(user_config_path=config_path)
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
    balance_provider = create_balance_provider(settings.base_url, settings.api_key)
    balance = await balance_provider.get_balance()
    status = create_status_info(settings.model_name, balance)
    await run_chat(
        client,
        status,
        settings,
        workspace,
        session_id,
        context_budget=ContextBudget(
            settings.context_window,
            settings.reserve_tokens,
            settings.keep_recent_tokens,
        ),
        mcp_provider=mcp_provider,
        max_tool_rounds=settings.max_tool_rounds,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """处理启动阶段的错误并返回进程退出码"""

    parser = argparse.ArgumentParser(description="Start epsilon")
    parser.add_argument(
        "--config",
        type=Path,
        help="Use a specific config file and skip first-run setup",
    )
    subparsers = parser.add_subparsers(dest="command")
    resume_parser = subparsers.add_parser("resume", help="Resume a previous session")
    resume_parser.add_argument("session_id", nargs="?", help="Session ID to resume")
    args = parser.parse_args(argv)

    try:
        asyncio.run(
            run(
                getattr(args, "session_id", None),
                resume=args.command == "resume",
                config_path=args.config,
            )
        )
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except SessionStoreError as exc:
        print(f"Session error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExited.")
    except Exception:
        logger.debug("Unexpected error during startup", exc_info=True)
        print(
            "Runtime error: unexpected failure, retry or check debug logs",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
