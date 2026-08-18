"""提供离线和在线评测所需的数据结构"""

from .models import EvaluationAssertion, EvaluationResult, EvaluationScenario
from .metrics import EvaluationMetrics, calculate_metrics
from .report import generate_report, render_report
from .scenarios import (
    FILE_EDIT_SCENARIO,
    MEMORY_SCENARIO,
    COMPACTION_RESTORE_SCENARIO,
    MODEL_RETRY_SCENARIO,
    TOOL_RECOVERY_SCENARIO,
    run_compaction_restore_scenario,
    run_file_edit_scenario,
    run_memory_scenario,
    run_tool_recovery_scenario,
    run_model_retry_scenario,
)
from .storage import append_result, load_results

__all__ = [
    "EvaluationAssertion",
    "EvaluationResult",
    "EvaluationScenario",
    "EvaluationMetrics",
    "calculate_metrics",
    "generate_report",
    "render_report",
    "append_result",
    "load_results",
    "MEMORY_SCENARIO",
    "FILE_EDIT_SCENARIO",
    "TOOL_RECOVERY_SCENARIO",
    "COMPACTION_RESTORE_SCENARIO",
    "MODEL_RETRY_SCENARIO",
    "run_compaction_restore_scenario",
    "run_file_edit_scenario",
    "run_memory_scenario",
    "run_tool_recovery_scenario",
    "run_model_retry_scenario",
]
