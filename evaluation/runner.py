"""执行离线评测场景并保存结果"""

import argparse
import asyncio
import tempfile
from pathlib import Path

from .report import generate_report
from .scenarios import (
    run_compaction_restore_scenario,
    run_file_edit_scenario,
    run_memory_scenario,
    run_model_retry_scenario,
    run_tool_recovery_scenario,
)
from .storage import append_result


async def run_offline(output_path: Path, report_path: Path):
    """在临时工作区执行五类离线场景并生成结果文件"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="864code-evaluation-") as directory:
        workspace = Path(directory)
        results = [
            await run_memory_scenario(),
            await run_file_edit_scenario(workspace),
            await run_tool_recovery_scenario(workspace),
            await run_compaction_restore_scenario(workspace),
            await run_model_retry_scenario(),
        ]
    for result in results:
        append_result(output_path, result)
    generate_report(report_path, results)
    return results


def main() -> int:
    """处理离线评测命令行参数"""

    parser = argparse.ArgumentParser(description="运行 864code 离线评测")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation-results/results.jsonl"),
        help="JSONL 结果文件路径",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evaluation-results/report.html"),
        help="HTML 报告路径",
    )
    args = parser.parse_args()
    results = asyncio.run(run_offline(args.output, args.report))
    passed = sum(result.passed for result in results)
    print(f"offline evaluation: {passed}/{len(results)} scenarios passed")
    print(f"results: {args.output}")
    print(f"report: {args.report}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
