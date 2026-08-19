"""生成评测 baseline 并比较新增回归"""

import json
from dataclasses import dataclass
from pathlib import Path

from .metrics import calculate_metrics
from .models import EvaluationResult

MAX_P95_DURATION_RATIO = 1.25
MAX_AVERAGE_MODEL_REQUEST_RATIO = 1.25


@dataclass(frozen=True)
class RegressionReport:
    """保存当前结果相对 baseline 的差异"""

    new_failures: tuple[str, ...]
    known_failures: tuple[str, ...]
    missing_runs: tuple[str, ...]
    duplicate_runs: tuple[str, ...]
    metric_regressions: tuple[str, ...] = ()
    metadata_mismatches: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """返回是否没有发现新增失败或结果结构问题"""

        return (
            not self.new_failures
            and not self.missing_runs
            and not self.duplicate_runs
            and not self.metric_regressions
            and not self.metadata_mismatches
        )


def create_baseline(
    results: list[EvaluationResult],
    metadata: dict[str, str] | None = None,
) -> dict[str, object]:
    """根据当前评测结果生成可保存的 baseline"""

    metrics = calculate_metrics(results)
    return {
        "schema_version": 2,
        "sample_count": len(results),
        "metadata": dict(metadata or {}),
        "metrics": {
            "task_completion_rate": metrics.task_completion_rate,
            "p95_duration_ms": metrics.p95_duration_ms,
            "average_model_requests": metrics.average_model_requests,
            "total_compactions": metrics.total_compactions,
        },
        "runs": [_run_record(result) for result in results],
    }


def compare_baseline(
    current: list[EvaluationResult],
    baseline: dict[str, object],
    metadata: dict[str, str] | None = None,
) -> RegressionReport:
    """比较当前结果并识别新增、已知、缺失和重复运行"""

    baseline_runs = _index_runs(baseline.get("runs", []))
    current_runs = _index_results(current)
    new_failures: list[str] = []
    known_failures: list[str] = []
    duplicate_runs: list[str] = []

    for key, results in current_runs.items():
        if len(results) > 1:
            duplicate_runs.append(key)
            continue
        result = results[0]
        if result.passed:
            continue
        if baseline_runs.get(key, {}).get("passed") is False:
            known_failures.append(key)
        else:
            new_failures.append(key)

    missing_runs = [key for key in baseline_runs if key not in current_runs]
    metric_regressions = _compare_metrics(current, baseline)
    metadata_mismatches = _compare_metadata(baseline, metadata)
    return RegressionReport(
        new_failures=tuple(sorted(new_failures)),
        known_failures=tuple(sorted(known_failures)),
        missing_runs=tuple(sorted(missing_runs)),
        duplicate_runs=tuple(sorted(duplicate_runs)),
        metric_regressions=metric_regressions,
        metadata_mismatches=metadata_mismatches,
    )


def write_baseline(path: Path, baseline: dict[str, object]) -> None:
    """将 baseline 写入 JSON 文件"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")


def load_baseline(path: Path) -> dict[str, object]:
    """从 JSON 文件读取 baseline"""

    return json.loads(path.read_text(encoding="utf-8"))


def _run_record(result: EvaluationResult) -> dict[str, object]:
    """保存单次运行的 baseline 信息"""

    return {
        "scenario": result.scenario,
        "repetition": result.repetition,
        "passed": result.passed,
    }


def _index_results(
    results: list[EvaluationResult],
) -> dict[str, list[EvaluationResult]]:
    """按场景和重复编号索引当前结果"""

    indexed: dict[str, list[EvaluationResult]] = {}
    for result in results:
        indexed.setdefault(_run_key(result.scenario, result.repetition), []).append(result)
    return indexed


def _index_runs(runs: object) -> dict[str, dict[str, object]]:
    """按场景和重复编号索引 baseline 结果"""

    if not isinstance(runs, list):
        raise ValueError("baseline runs 必须是数组")
    indexed: dict[str, dict[str, object]] = {}
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("baseline run 必须是对象")
        key = _run_key(str(run.get("scenario")), int(run.get("repetition", 1)))
        indexed[key] = run
    return indexed


def _run_key(scenario: str, repetition: int) -> str:
    """生成稳定的运行标识"""

    return f"{scenario}#{repetition}"


def _compare_metrics(
    current: list[EvaluationResult],
    baseline: dict[str, object],
) -> tuple[str, ...]:
    """比较 baseline 中已记录的关键性能与质量指标。"""

    baseline_metrics = baseline.get("metrics")
    if not isinstance(baseline_metrics, dict):
        return ()
    current_metrics = calculate_metrics(current)
    regressions: list[str] = []
    previous_rate = baseline_metrics.get("task_completion_rate")
    if isinstance(previous_rate, (int, float)) and current_metrics.task_completion_rate < previous_rate:
        regressions.append("任务成功率下降")
    previous_p95 = baseline_metrics.get("p95_duration_ms")
    if (
        isinstance(previous_p95, (int, float))
        and previous_p95 > 0
        and current_metrics.p95_duration_ms > previous_p95 * MAX_P95_DURATION_RATIO
    ):
        regressions.append("P95 延迟增加超过 25%")
    previous_requests = baseline_metrics.get("average_model_requests")
    if (
        isinstance(previous_requests, (int, float))
        and current_metrics.average_model_requests
        > previous_requests * MAX_AVERAGE_MODEL_REQUEST_RATIO
    ):
        regressions.append("平均模型请求数增加超过 25%")
    previous_compactions = baseline_metrics.get("total_compactions")
    if (
        isinstance(previous_compactions, int)
        and current_metrics.total_compactions > previous_compactions
    ):
        regressions.append("总上下文压缩次数增加")
    return tuple(regressions)


def _compare_metadata(
    baseline: dict[str, object],
    metadata: dict[str, str] | None,
) -> tuple[str, ...]:
    """比较评测配置，避免跨模型或跨场景误用 baseline。"""

    baseline_metadata = baseline.get("metadata")
    if not isinstance(baseline_metadata, dict) or metadata is None:
        return ()
    mismatches = [
        key
        for key, value in metadata.items()
        if baseline_metadata.get(key) != value
    ]
    return tuple(sorted(mismatches))
