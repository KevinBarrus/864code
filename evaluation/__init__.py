"""提供离线和在线评测所需的数据结构"""

from .models import EvaluationAssertion, EvaluationResult, EvaluationScenario
from .scenarios import (
    FILE_EDIT_SCENARIO,
    MEMORY_SCENARIO,
    COMPACTION_RESTORE_SCENARIO,
    TOOL_RECOVERY_SCENARIO,
    run_compaction_restore_scenario,
    run_file_edit_scenario,
    run_memory_scenario,
    run_tool_recovery_scenario,
)

__all__ = [
    "EvaluationAssertion",
    "EvaluationResult",
    "EvaluationScenario",
    "MEMORY_SCENARIO",
    "FILE_EDIT_SCENARIO",
    "TOOL_RECOVERY_SCENARIO",
    "COMPACTION_RESTORE_SCENARIO",
    "run_compaction_restore_scenario",
    "run_file_edit_scenario",
    "run_memory_scenario",
    "run_tool_recovery_scenario",
]
