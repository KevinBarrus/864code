"""根据统一错误模型生成 Agent 的恢复决策。"""

from dataclasses import dataclass
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
    "network": ErrorDecision("retry", max_attempts=1),
    "timeout": ErrorDecision("retry", max_attempts=1),
    "rate_limit": ErrorDecision("retry", delay_seconds=1, max_attempts=1),
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
        if decision.visible_message:
            return decision
        return ErrorDecision(
            action=decision.action,
            delay_seconds=decision.delay_seconds,
            max_attempts=decision.max_attempts,
            visible_message=error.user_message,
        )
