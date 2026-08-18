"""生成评测 baseline 并比较新增回归"""

import json
from dataclasses import dataclass
from pathlib import Path

from .metrics import calculate_metrics
from .models import EvaluationResult


@dataclass(frozen=True)
class RegressionReport:
    """保存当前结果相对 baseline 的差异"""

    new_failures: tuple[str, ...]
    known_failures: tuple[str, ...]
    missing_runs: tuple[str, ...]
    duplicate_runs: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """返回是否没有发现新增失败或结果结构问题"""

        return not self.new_failures and not self.missing_runs and not self.duplicate_runs


def create_baseline(results: list[EvaluationResult]) -> dict[str, object]:
    """根据当前评测结果生成可保存的 baseline"""

    metrics = calculate_metrics(results)
    return {
        "schema_version": 1,
        "sample_count": len(results),
        "pass_rate": metrics.task_completion_rate,
        "p50_duration_ms": metrics.p50_duration_ms,
        "p95_duration_ms": metrics.p95_duration_ms,
        "runs": [_run_record(result) for result in results],
    }


def compare_baseline(
    current: list[EvaluationResult],
    baseline: dict[str, object],
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
    return RegressionReport(
        new_failures=tuple(sorted(new_failures)),
        known_failures=tuple(sorted(known_failures)),
        missing_runs=tuple(sorted(missing_runs)),
        duplicate_runs=tuple(sorted(duplicate_runs)),
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
