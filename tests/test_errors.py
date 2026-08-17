from core.errors import AgentError, is_error_category


def test_agent_error_separates_safe_messages_from_cause() -> None:
    cause = RuntimeError("secret stack detail")
    error = AgentError(
        category="network",
        operation="model_request",
        user_message="模型请求失败",
        model_message="模型请求暂时不可用",
        retryable=True,
        cause=cause,
    )

    assert str(error) == "模型请求失败"
    assert error.model_message == "模型请求暂时不可用"
    assert error.cause is cause
    assert "secret stack detail" not in str(error)


def test_is_error_category_rejects_unknown_values() -> None:
    assert is_error_category("timeout")
    assert not is_error_category("unknown")
