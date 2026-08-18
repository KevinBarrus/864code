from pathlib import Path

from evaluation.models import EvaluationAssertion, EvaluationResult
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
    assert "P50 耗时" in html
    assert "P95 耗时" in html
    assert "demo" in html
    assert "通过" in html


def test_generate_report_writes_static_html(tmp_path: Path) -> None:
    """测试报告可以写入静态 HTML 文件"""

    path = tmp_path / "evaluation-report.html"
    generate_report(path, [])

    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
