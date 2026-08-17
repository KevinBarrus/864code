from core.error_policy import AgentErrorPolicy
from core.errors import AgentError


def make_error(category: str) -> AgentError:
    return AgentError(category, "test_operation", "安全错误信息")  # type: ignore[arg-type]


def test_policy_retries_network_errors_once() -> None:
    decision = AgentErrorPolicy().decide(make_error("network"))

    assert decision.action == "retry"
    assert decision.max_attempts == 1
    assert decision.visible_message == "安全错误信息"


def test_policy_returns_tool_errors_to_model() -> None:
    decision = AgentErrorPolicy().decide(make_error("tool_execution"))

    assert decision.action == "continue"
    assert decision.max_attempts == 0


def test_policy_uses_fallback_for_context_errors() -> None:
    decision = AgentErrorPolicy().decide(make_error("context_compaction"))

    assert decision.action == "fallback"
    assert decision.max_attempts == 1


def test_policy_does_not_retry_authentication_errors() -> None:
    decision = AgentErrorPolicy().decide(make_error("authentication"))

    assert decision.action == "stop"
    assert decision.max_attempts == 0
