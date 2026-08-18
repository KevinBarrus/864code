"""提供离线和在线评测所需的数据结构"""

from .models import EvaluationAssertion, EvaluationResult, EvaluationScenario
from .scenarios import MEMORY_SCENARIO, run_memory_scenario

__all__ = [
    "EvaluationAssertion",
    "EvaluationResult",
    "EvaluationScenario",
    "MEMORY_SCENARIO",
    "run_memory_scenario",
]
