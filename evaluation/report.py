"""将评测结果渲染为可直接打开的静态 HTML 报告"""

from html import escape
from pathlib import Path

from .baseline import RegressionReport
from .metrics import calculate_metrics
from .models import EvaluationResult


def generate_report(
    path: Path,
    results: list[EvaluationResult],
    regression: RegressionReport | None = None,
) -> None:
    """根据评测结果生成静态 HTML 文件"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(results, regression), encoding="utf-8")


def render_report(
    results: list[EvaluationResult],
    regression: RegressionReport | None = None,
) -> str:
    """将评测结果转换为 HTML 文本"""

    metrics = calculate_metrics(results)
    rows = "\n".join(_result_row(result) for result in results)
    failures = "\n".join(_failure_row(result) for result in results for assertion in result.assertions if not assertion.passed)
    failures = failures or "<tr><td colspan=3>无失败断言</td></tr>"
    regression_html = _regression_section(regression)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>864code Evaluation Report</title>
  <style>
    body {{ font-family: sans-serif; max-width: 1100px; margin: 2rem auto; color: #222; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .75rem; }}
    .metric {{ padding: 1rem; background: #f1f3f5; border-radius: .4rem; }}
    .value {{ display: block; font-size: 1.5rem; font-weight: bold; margin-top: .35rem; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0 2rem; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: .6rem; text-align: left; }}
    .pass {{ color: #16803c; }}
    .fail {{ color: #b42318; }}
  </style>
</head>
<body>
  <h1>864code Evaluation Report</h1>
  <p>样本数：{metrics.scenario_count}，通过数：{metrics.passed_scenarios}</p>
  <p>核心链路回归用于验证模块协作，真实任务评测才用于衡量模型完成任务的能力</p>
  <section class="metrics">
    {_metric("任务完成率", _percent(metrics.task_completion_rate))}
    {_metric("断言通过率", _percent(metrics.assertion_pass_rate))}
    {_metric("工具成功率", _percent(metrics.tool_success_rate))}
    {_metric("工具恢复率", _percent(metrics.tool_recovery_rate))}
    {_metric("持久化成功率", _percent(metrics.persistence_success_rate))}
    {_metric("降级率", _percent(metrics.degradation_rate))}
    {_metric("平均耗时", f"{metrics.average_duration_ms:.2f} ms")}
    {_metric("P50 耗时", f"{metrics.p50_duration_ms:.2f} ms")}
    {_metric("P95 耗时", f"{metrics.p95_duration_ms:.2f} ms")}
    {_metric("平均模型请求", f"{metrics.average_model_requests:.2f}")}
    {_metric("平均请求耗时", f"{metrics.average_model_request_duration_ms:.2f} ms")}
    {_metric("请求 P50", f"{metrics.p50_model_request_duration_ms:.2f} ms")}
    {_metric("请求 P95", f"{metrics.p95_model_request_duration_ms:.2f} ms")}
  </section>
  <h2>场景结果</h2>
  <table>
    <thead><tr><th>场景</th><th>类型</th><th>状态</th><th>错误类别</th><th>失败阶段</th><th>错误详情</th><th>耗时</th><th>模型请求</th><th>工具调用</th><th>重试</th><th>压缩</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <h2>失败断言</h2>
  <table>
    <thead><tr><th>场景</th><th>断言</th><th>原因</th></tr></thead>
    <tbody>{failures}</tbody>
  </table>
  {regression_html}
</body>
</html>
"""


def _result_row(result: EvaluationResult) -> str:
    """生成单个场景的 HTML 行"""

    status = "通过" if result.passed else "失败"
    status_class = "pass" if result.passed else "fail"
    return (
        f"<tr><td>{escape(result.scenario)}</td>"
        f"<td>{_evaluation_type_label(result.evaluation_type)}</td>"
        f"<td class=\"{status_class}\">{status}</td>"
        f"<td>{escape(result.error_category or '-')}</td>"
        f"<td>{escape(result.error_stage or '-')}</td>"
        f"<td>{escape(result.error_message or '-')}</td>"
        f"<td>{result.duration_ms:.2f} ms</td>"
        f"<td>{result.model_requests}</td><td>{result.tool_calls}</td>"
        f"<td>{result.retries}</td><td>{result.compactions}</td></tr>"
    )


def _evaluation_type_label(evaluation_type: str) -> str:
    """将评测类型转换为报告中的中文标签。"""

    labels = {
        "core-regression": "核心链路回归",
        "real-task": "真实任务",
        "online-special": "在线专项",
    }
    return labels[evaluation_type]


def _failure_row(result: EvaluationResult) -> str:
    """生成失败断言的 HTML 行"""

    assertion = next(assertion for assertion in result.assertions if not assertion.passed)
    return (
        f"<tr><td>{escape(result.scenario)}</td>"
        f"<td>{escape(assertion.name)}</td>"
        f"<td>{escape(assertion.message)}</td></tr>"
    )


def _metric(name: str, value: str) -> str:
    """生成指标卡片"""

    return f'<div class="metric">{escape(name)}<span class="value">{escape(value)}</span></div>'


def _percent(value: float) -> str:
    """将比例格式化为百分比"""

    return f"{value:.1%}"


def _regression_section(regression: RegressionReport | None) -> str:
    """生成 baseline 回归比较区域"""

    if regression is None:
        return ""
    status = "通过" if regression.passed else "失败"
    status_class = "pass" if regression.passed else "fail"
    return f"""<h2>Baseline 回归</h2>
<p class="{status_class}">回归门禁：{status}</p>
<ul>
  <li>新增失败：{_list_or_none(regression.new_failures)}</li>
  <li>历史已知失败：{_list_or_none(regression.known_failures)}</li>
  <li>缺失运行：{_list_or_none(regression.missing_runs)}</li>
  <li>重复运行：{_list_or_none(regression.duplicate_runs)}</li>
  <li>指标回归：{_list_or_none(regression.metric_regressions)}</li>
  <li>配置不匹配：{_list_or_none(regression.metadata_mismatches)}</li>
</ul>"""


def _list_or_none(values: tuple[str, ...]) -> str:
    """格式化回归项列表"""

    return escape(", ".join(values) if values else "无")
