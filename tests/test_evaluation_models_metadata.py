from evaluation.models import EvaluationResult


def test_evaluation_result_generates_run_id_and_default_repetition() -> None:
    """测试评测结果默认生成运行标识和重复编号"""

    result = EvaluationResult("scenario", 1)

    assert result.run_id
    assert result.repetition == 1
    assert result.events == ()
