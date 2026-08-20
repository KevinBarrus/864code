# 记忆系统实现计划

## 1. 目标与范围

本阶段只实现“当前进程内的单会话消息记忆”，解决连续提问时模型看不到前文的问题。

必须支持：

- 保存用户消息和模型消息；
- 按追加顺序读取完整历史；
- 每次模型请求发送当前会话历史；
- 流式回复结束或取消后，将已生成内容写回记忆；
- 记忆逻辑与 TUI 展示逻辑分离。

暂不实现：

- JSONL 或其他持久化；
- 多会话、会话恢复和分支；
- 上下文长度计算、裁剪和摘要；
- 向量检索、长期记忆和自动反思；
- 工具调用和 Agent 循环。

理由：先验证最基本的“历史保存 → 历史发送 → 回复追加”闭环，避免在消息历史尚未稳定时引入更多状态。

## 2. 唯一设计方案

### 2.1 记忆对象

新增 `src/core/memory.py`，使用一个简单的 `Memory` 类保存：

```python
list[Message]
```

对外只提供三个操作：

```python
add_user_message(content: str) -> None
add_assistant_message(content: str) -> None
get_messages() -> list[Message]
```

`get_messages()` 返回新的列表，调用方不能直接修改 Memory 内部历史。暂不提供删除、搜索、分支和持久化接口。

该方案参考 Pi 的 Session 消息追加和“内部历史独立于模型请求”的思想，但在第一版只保留消息列表，不引入 Pi 的事件树和 JSONL 存储。

### 2.2 对话与模型上下文

本阶段将 `Memory` 中的 `Message` 直接作为模型请求参数：

```text
用户输入
  ↓
Memory.add_user_message
  ↓
Memory.get_messages
  ↓
ModelClient.stream_chat
  ↓
Memory.add_assistant_message
```

暂不建立单独的上下文转换层。这样保留了未来增加系统消息、工具消息和上下文裁剪的入口，同时不为当前只有三种消息角色的需求提前增加抽象。

该方案参考 Pi 的消息历史与模型消息分离原则；当前阶段的模型视图与历史视图内容相同，只是通过接口边界保留后续演进空间。

### 2.3 取消请求

取消请求时保留已经生成的模型文本：

- 流式过程中持续追加到 TUI 当前回复；
- 请求正常结束或被取消后，将当前回复全文追加为一条 assistant message；
- UI 继续显示“已取消”提示，但该提示不写入模型记忆；
- 如果请求在产生任何文本前取消，则追加空回复没有意义，直接不写入 assistant message。

该行为与当前 TUI 约定一致，保证界面展示和下一轮模型上下文一致。

## 3. 代码改动计划

### 第一步：实现 Memory

文件：`src/core/memory.py`

- 定义 `Memory` 类；
- 使用 `Message` 作为唯一消息数据结构；
- 初始化为空历史；
- 追加用户消息和模型消息；
- 读取历史时返回副本；
- 为新类和新方法添加中文注释。

不修改 `screen.py`，因为它只负责展示和输入交互。

### 第二步：接入应用层

文件：`src/core/ui.py`

- 在 `run_chat()` 中创建一个 `Memory` 实例；
- `handle_submit()` 先追加用户消息；
- 调用模型时传入 `memory.get_messages()`；
- 流式收集模型文本，同时继续更新 TUI；
- 请求结束后，将完整文本追加为 assistant message；
- 取消时保留已生成文本，再重新抛出 `CancelledError`，维持现有输入恢复逻辑；
- 不让 `screen.py` 直接依赖 `Memory`。

### 第三步：更新模块说明

文件：`src/core/AGENTS.md`

补充 `memory.py` 的职责和边界：

- 只负责当前进程内的会话消息；
- 不负责 TUI 展示、模型请求、持久化、检索和上下文裁剪。

## 4. 测试计划

### Memory 单元测试

新增 `tests/test_memory.py`，只覆盖必要行为：

1. 初始历史为空；
2. 用户消息和 assistant 消息按追加顺序保存；
3. `get_messages()` 返回的列表被外部修改时，不影响内部历史；
4. 返回的消息角色和内容正确。

### 应用层测试

更新 `tests/test_ui.py`：

1. 第一次请求发送一条 user 消息；
2. 第二次请求发送第一次完整的 user/assistant 消息以及第二次 user 消息；
3. 流式回复被完整写入 Memory；
4. 取消请求后，已生成的部分回复仍出现在下一次请求的历史中；
5. “（已取消）”只展示在 TUI，不发送给模型。

测试使用现有 Fake Model Client，不增加新的测试依赖。

## 5. 验收标准

- `uv run pytest` 全部通过；
- 连续提问时，Fake Model Client 能收到完整历史；
- 取消请求后，部分 assistant 回复可以被下一轮模型看到；
- TUI 的布局、滚动、输入恢复和快捷键行为不改变；
- `screen.py` 不包含记忆逻辑；
- 本阶段没有新增数据库、向量库、摘要模型或持久化文件。

## 6. 后续扩展顺序

只有本阶段稳定后，按以下顺序继续：

1. 将 `Memory` 历史转换为独立的模型上下文视图；
2. 增加 JSONL 会话持久化和恢复；
3. 增加上下文预算与旧消息压缩；
4. 增加工具消息和真正的 Agent Loop；
5. 再评估是否需要跨会话长期记忆。

持久化方向参考 Pi 的 JSONL append-only Session；上下文压缩方向参考 Codex 的结构化历史和 Hermes 的独立 Context Engine，但本阶段不提前实现这些能力。
