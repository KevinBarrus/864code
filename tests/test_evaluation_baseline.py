from pathlib import Path

from evaluation.baseline import (
    compare_baseline,
    create_baseline,
    load_baseline,
    write_baseline,
)
from evaluation.models import EvaluationAssertion, EvaluationResult


def _result(
    scenario: str,
    repetition: int,
    passed: bool,
    *,
    duration_ms: float = 10,
    model_requests: int = 1,
    compactions: int = 0,
) -> EvaluationResult:
    """构造测试用运行结果"""

    return EvaluationResult(
        scenario=scenario,
        duration_ms=duration_ms,
        repetition=repetition,
        model_requests=model_requests,
        compactions=compactions,
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


def test_baseline_detects_metric_regressions() -> None:
    """测试性能或压缩次数明显恶化会触发回归。"""

    baseline = create_baseline(
        [
            _result(
                "task",
                1,
                True,
                duration_ms=100,
                model_requests=2,
                compactions=1,
            )
        ]
    )
    report = compare_baseline(
        [
            _result(
                "task",
                1,
                True,
                duration_ms=130,
                model_requests=3,
                compactions=2,
            )
        ],
        baseline,
    )

    assert report.metric_regressions == (
        "P95 延迟增加超过 25%",
        "平均模型请求数增加超过 25%",
        "总上下文压缩次数增加",
    )
    assert not report.passed


def test_baseline_rejects_different_evaluation_metadata() -> None:
    """测试不同模型或配置不会复用同一 baseline。"""

    baseline = create_baseline(
        [_result("task", 1, True)],
        {"model_name": "model-a", "scenario_version": "1"},
    )

    report = compare_baseline(
        [_result("task", 1, True)],
        baseline,
        {"model_name": "model-b", "scenario_version": "1"},
    )

    assert report.metadata_mismatches == ("model_name",)
    assert not report.passed
