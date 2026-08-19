"""定义跨模块使用的统一错误模型。"""

from typing import Literal


ErrorCategory = Literal[
    "network",
    "timeout",
    "rate_limit",
    "authentication",
    "invalid_request",
    "tool_execution",
    "tool_permission",
    "session_persistence",
    "context_compaction",
    "context_overflow",
    "internal",
]


class AgentError(RuntimeError):
    """描述一次需要由 AgentErrorPolicy 决策的跨模块错误。"""

    def __init__(
        self,
        category: ErrorCategory,
        operation: str,
        user_message: str,
        model_message: str | None = None,
        retryable: bool = False,
        cause: BaseException | None = None,
    ) -> None:
        """保存安全展示信息和仅供内部诊断的原始异常。"""

        super().__init__(user_message)
        self.category = category
        self.operation = operation
        self.user_message = user_message
        self.model_message = model_message
        self.retryable = retryable
        self.cause = cause


def is_error_category(value: object) -> bool:
    """判断外部输入是否属于受支持的错误类别。"""

    return value in {
        "network",
        "timeout",
        "rate_limit",
        "authentication",
        "invalid_request",
        "tool_execution",
        "tool_permission",
        "session_persistence",
        "context_compaction",
        "context_overflow",
        "internal",
    }
