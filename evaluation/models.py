"""定义评测场景、断言和结果的数据结构"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationScenario:
    """描述一个可重复执行的评测场景"""

    name: str
    description: str


@dataclass(frozen=True)
class EvaluationAssertion:
    """记录一条评测断言及其失败原因"""

    name: str
    passed: bool
    message: str = ""


@dataclass(frozen=True)
class EvaluationResult:
    """保存单次场景运行的统计信息和断言结果"""

    scenario: str
    duration_ms: float
    model_requests: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    retries: int = 0
    compactions: int = 0
    estimated_tokens: int = 0
    actual_tokens: int | None = None
    persistence_degraded: bool = False
    assertions: tuple[EvaluationAssertion, ...] = ()

    @property
    def passed(self) -> bool:
        """返回场景是否通过全部断言"""

        return all(assertion.passed for assertion in self.assertions)
