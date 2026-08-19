from pathlib import Path

import pytest

from evaluation.runner import run_offline
from evaluation.storage import load_results


@pytest.mark.asyncio
async def test_run_offline_executes_all_scenarios_and_writes_outputs(
    tmp_path: Path,
) -> None:
    """测试离线入口执行全部场景并生成 JSONL 和 HTML"""

    results_path = tmp_path / "results.jsonl"
    report_path = tmp_path / "report.html"

    results = await run_offline(results_path, report_path)

    assert len(results) == 6
    assert all(result.passed for result in results)
    assert len(load_results(results_path)) == 6
    assert report_path.exists()
