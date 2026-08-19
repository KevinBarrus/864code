# 问题 3：复查中发现的新问题（非第二轮 28 条）

## 发现来源

本问题整理自对 `problem2.md` 所提 28 个问题的复查。复查中除确认大部分问题已修复外，还发现以下 4 个新的系统性问题，均不在原 28 条范围内。

## 问题一：模型超时是「总时长」而非「无数据间隔」

`openai_client.py:76` 的 `asyncio.timeout` 包住 `create()` + 整个流式循环，120s 是整条回复的累计上限。长回复/多次工具调用会被正常请求误判为超时杀掉。生产级应改用「首个字节前超时 + 流式数据间隔超时」组合，而不是一刀切总时长。

## 问题二：P95 回归门禁实际形同虚设

`baseline.py:12` 的 `MIN_PERFORMANCE_SAMPLE_COUNT=20`，而 `online.py:459` 默认 6 次 × 3 任务 = 18 样本，`_has_stable_performance_samples` 恒为 False，P95 比较永远不触发；但同时「平均模型请求数 >25%」这条没有样本门槛仍在生效，18 样本下仍有噪声误报风险。两个门槛的策略不一致。

## 问题三：`context_overflow` 识别依赖错误文本子串

`openai_client.py:128-135` 的 `_is_context_overflow_error` 靠匹配 `"context length" / "maximum context"` 等英文子串，对返回中文/其他语言错误信息的服务端会失效，退回 `invalid_request`→`stop`。本质上是「仍无真实 tokenizer」的下游残留。

## 问题四：`_has_expected_tool_order` 约束偏严

`online.py` 的 `_has_expected_tool_order` 用 `max(read) < min(edit)` 要求所有读都先于所有写，对「读一个改一个、再读再改」的自然实现会产生假阴性（当前 prompt 明确要求先全读后全改，故可接受，但约束和 prompt 强耦合）。
