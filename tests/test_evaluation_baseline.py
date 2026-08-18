from pathlib import Path

from evaluation.baseline import (
    compare_baseline,
    create_baseline,
    load_baseline,
    write_baseline,
)
from evaluation.models import EvaluationAssertion, EvaluationResult


def _result(scenario: str, repetition: int, passed: bool) -> EvaluationResult:
    """构造测试用运行结果"""

    return EvaluationResult(
        scenario=scenario,
        duration_ms=10,
        repetition=repetition,
        assertions=(EvaluationAssertion("done", passed),),
    )


def test_baseline_round_trip_and_regression_classification(tmp_path: Path) -> None:
    """测试 baseline 保存以及新增、已知、缺失和重复结果分类"""

    baseline = create_baseline(
        [_result("task", 1, True), _result("known", 1, False)]
    )
    path = tmp_path / "baseline.json"
    write_baseline(path, baseline)

    current = [
        _result("task", 1, False),
        _result("known", 1, False),
        _result("new", 1, False),
        _result("new", 1, False),
    ]
    report = compare_baseline(current, load_baseline(path))

    assert report.new_failures == ("task#1",)
    assert report.known_failures == ("known#1",)
    assert report.missing_runs == ()
    assert report.duplicate_runs == ("new#1",)
    assert not report.passed


def test_baseline_detects_missing_runs() -> None:
    """测试 baseline 可以发现缺失的重复运行"""

    baseline = create_baseline([_result("task", 1, True), _result("task", 2, True)])

    report = compare_baseline([_result("task", 1, True)], baseline)

    assert report.missing_runs == ("task#2",)
