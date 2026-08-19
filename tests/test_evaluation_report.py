from pathlib import Path

from evaluation.models import EvaluationAssertion, EvaluationResult
from evaluation.baseline import RegressionReport
from evaluation.report import generate_report, render_report


def test_render_report_contains_metrics_and_scenario_status() -> None:
    """测试报告包含核心指标和场景状态"""

    html = render_report(
        [
            EvaluationResult(
                scenario="demo",
                duration_ms=12,
                assertions=(EvaluationAssertion("done", True),),
            )
        ]
    )

    assert "任务完成率" in html
    assert "核心链路回归" in html
    assert "真实任务评测才用于衡量模型完成任务的能力" in html
    assert "P50 耗时" in html
    assert "P95 耗时" in html
    assert "demo" in html
    assert "通过" in html


def test_render_report_contains_baseline_regression() -> None:
    """测试报告包含 baseline 回归结果"""

    html = render_report(
        [],
        RegressionReport(
            new_failures=("task#1",),
            known_failures=(),
            missing_runs=(),
            duplicate_runs=(),
        ),
    )

    assert "新增失败" in html
    assert "指标回归" in html
    assert "配置不匹配" in html
    assert "task#1" in html
    assert "回归门禁：失败" in html


def test_generate_report_writes_static_html(tmp_path: Path) -> None:
    """测试报告可以写入静态 HTML 文件"""

    path = tmp_path / "evaluation-report.html"
    generate_report(path, [])

    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
