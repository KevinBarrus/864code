from pathlib import Path

from evaluation.metrics import calculate_metrics
from evaluation.models import EvaluationAssertion, EvaluationResult
from evaluation.storage import append_result, load_results


def _result(
    scenario: str,
    passed: bool,
    *,
    tool_calls: int = 0,
    tool_failures: int = 0,
    persistence_degraded: bool = False,
) -> EvaluationResult:
    """构造测试用评测结果"""

    return EvaluationResult(
        scenario=scenario,
        duration_ms=10,
        model_requests=2,
        tool_calls=tool_calls,
        tool_failures=tool_failures,
        retries=1,
        compactions=1,
        persistence_degraded=persistence_degraded,
        assertions=(EvaluationAssertion("result", passed),),
    )


def test_calculate_metrics_aggregates_task_tool_and_recovery_rates() -> None:
    """测试指标计算覆盖任务、工具和异常恢复数据"""

    metrics = calculate_metrics(
        [
            _result("success", True, tool_calls=2),
            _result("recovery", True, tool_calls=2, tool_failures=1),
            _result("failed", False, persistence_degraded=True),
        ]
    )

    assert metrics.scenario_count == 3
    assert metrics.passed_scenarios == 2
    assert metrics.task_completion_rate == 2 / 3
    assert metrics.tool_success_rate == 3 / 4
    assert metrics.tool_recovery_rate == 1
    assert metrics.persistence_success_rate == 2 / 3
    assert metrics.total_retries == 3


def test_results_can_round_trip_through_jsonl(tmp_path: Path) -> None:
    """测试评测结果可以写入并从 JSONL 恢复"""

    path = tmp_path / "results.jsonl"
    expected = _result("round-trip", True, tool_calls=1)
    expected = EvaluationResult(
        scenario=expected.scenario,
        duration_ms=expected.duration_ms,
        run_id="run-1",
        repetition=2,
        model_requests=expected.model_requests,
        tool_calls=expected.tool_calls,
        tool_failures=expected.tool_failures,
        retries=expected.retries,
        compactions=expected.compactions,
        persistence_degraded=expected.persistence_degraded,
        events=({"type": "tool_call", "name": "read_file"},),
        assertions=expected.assertions,
    )

    append_result(path, expected)

    assert load_results(path) == [expected]
