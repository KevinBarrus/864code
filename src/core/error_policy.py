"""根据统一错误模型生成 Agent 的恢复决策。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Literal

from .errors import AgentError, ErrorCategory


ErrorAction = Literal["retry", "continue", "fallback", "stop"]


@dataclass(frozen=True)
class ErrorDecision:
    """描述上层应该执行的错误处理动作。"""

    action: ErrorAction
    delay_seconds: float = 0
    max_attempts: int = 0
    visible_message: str = ""


_ERROR_POLICIES: dict[ErrorCategory, ErrorDecision] = {
    "network": ErrorDecision("retry", max_attempts=2),
    "timeout": ErrorDecision("retry", max_attempts=2),
    "rate_limit": ErrorDecision("retry", max_attempts=2),
    "authentication": ErrorDecision("stop"),
    "invalid_request": ErrorDecision("stop"),
    "tool_execution": ErrorDecision("continue"),
    "tool_permission": ErrorDecision("continue"),
    "session_persistence": ErrorDecision("retry", max_attempts=2),
    "context_compaction": ErrorDecision("fallback", max_attempts=1),
    "context_overflow": ErrorDecision("stop"),
    "internal": ErrorDecision("stop"),
}


class AgentErrorPolicy:
    """集中维护错误类别到恢复动作的映射。"""

    def decide(self, error: AgentError) -> ErrorDecision:
        """根据错误类别返回不可变的处理决策。"""

        decision = _ERROR_POLICIES[error.category]
        retry_after = _retry_after_seconds(error) if error.category == "rate_limit" else None
        if decision.visible_message:
            return decision
        return ErrorDecision(
            action=decision.action,
            delay_seconds=retry_after if retry_after is not None else decision.delay_seconds,
            max_attempts=decision.max_attempts,
            visible_message=error.user_message,
        )


def _retry_after_seconds(error: AgentError) -> float | None:
    """读取底层 HTTP 响应中的 Retry-After 秒数或日期。"""

    response = getattr(error.cause, "response", None)
    headers = getattr(response, "headers", {})
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not isinstance(value, str):
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(
                0,
                (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds(),
            )
        except (TypeError, ValueError):
            return None
