"""定义可重复执行的离线评测场景"""

from time import perf_counter

from core.agent_loop import AgentLoop
from core.memory import Memory
from core.model import Message, TextDelta
from core.tools import ToolManager

from .fakes import FakeModelClient
from .models import EvaluationAssertion, EvaluationResult, EvaluationScenario


MEMORY_SCENARIO = EvaluationScenario(
    name="multi_turn_memory",
    description="验证多轮请求会携带之前的对话历史",
)


async def run_memory_scenario() -> EvaluationResult:
    """运行多轮记忆场景并返回结构化结果"""

    client = FakeModelClient(
        [
            [TextDelta("我记住了项目目标")],
            [TextDelta("根据之前的目标继续执行")],
        ]
    )
    memory = Memory()
    loop = AgentLoop(client, ToolManager())
    started_at = perf_counter()

    memory.add_user_message("项目目标是实现一个简洁的 Coding Agent")
    first_result = await loop.run(memory.get_messages())
    memory.add_message(first_result.messages[-1])

    memory.add_user_message("继续执行")
    second_result = await loop.run(memory.get_messages())

    has_history = (
        len(client.requests) == 2
        and client.requests[1][0]
        == Message(role="user", content="项目目标是实现一个简洁的 Coding Agent")
        and client.requests[1][1]
        == Message(role="assistant", content="我记住了项目目标")
    )
    assertions = (
        EvaluationAssertion("history-forwarded", has_history, "第二轮未携带第一轮历史"),
        EvaluationAssertion(
            "final-response",
            second_result.final_content == "根据之前的目标继续执行",
            "第二轮模型回复不符合预期",
        ),
    )
    return EvaluationResult(
        scenario=MEMORY_SCENARIO.name,
        duration_ms=(perf_counter() - started_at) * 1000,
        model_requests=len(client.requests),
        estimated_tokens=sum(
            len(message.content) // 4 for request in client.requests for message in request
        ),
        assertions=assertions,
    )
