# 问题 4：第三轮修复引入的新问题

## 发现来源

本问题整理自对 `problem3.md` 四个修复的复查。四个修复的生产代码均正确、测试 261 passed，但复查发现以下两个新问题。

## 问题一：测试套件从 4.5s 退化到 2 分钟

`--durations` 定位到唯一慢测试：

```
120.09s  tests/test_openai_client.py::test_client_times_out_when_stream_hangs
```

根因有两层：

1. 测试 bug：`test_openai_client.py:181-186` 构造了 `Settings(request_timeout_seconds=0.01)`，但没有设置新增的 `first_byte_timeout_seconds` / `stream_idle_timeout_seconds`。`SlowStream.__anext__` 永久挂起（`await asyncio.Event().wait()`），于是 `_stream_chunks` 里的 `asyncio.timeout(120.0)` 要等满 120 秒才触发。

2. 设计不一致（更本质）：`Settings` 数据类（`config.py:35-36`）把两个新字段的默认值写死为 `120.0`，且没有 `__post_init__` 做「未显式设置时回落到 `request_timeout_seconds`」的逻辑。这个回落逻辑只存在于 `load_settings`（`config.py:59-68`，从 `.env` 读取时生效）。所以凡是直接 `Settings(...)` 构造的代码路径（测试、以及将来任何不走 `.env` 的入口），只要只传了 `request_timeout_seconds`，新字段就会静默落到 120s，`request_timeout_seconds` 被无视。

建议修复（二选一或都做）：

- 治标：给 `test_client_times_out_when_stream_hangs` 补上 `first_byte_timeout_seconds=0.01, stream_idle_timeout_seconds=0.01`。
- 治本：把回落逻辑放进 `Settings.__post_init__`，让两个新字段默认值为 `None`，`__post_init__` 里 `None → request_timeout_seconds`，这样直接构造 `Settings` 也能拿到一致的超时，`load_settings` 里那段「缺省回落」就变成冗余可以删掉。

## 问题二：`context_overflow` 识别 code 匹配集偏窄（残留）

`_is_context_overflow_error` 只匹配 3 个特定 code（`context_length_exceeded` / `context_window_exceeded` / `max_context_length_exceeded`）。如果某服务端只在 `type` 里返回 `invalid_request_error`、把「上下文超长」细节只放在 `message` 文本里（不设专门 code），仍会漏判、回落到 `invalid_request`→`stop`。方向比原来的文本子串匹配更健壮，但这个边界仍存在。是否要补一个「code 优先、message 兜底」的降级，属于非阻塞优化。
