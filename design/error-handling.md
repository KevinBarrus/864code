# 异常处理方案

## 一、设计目标

异常处理采用统一策略层，避免模型、工具、Session、上下文和 UI 各自处理异常

```text
底层模块识别异常
        ↓
转换为 AgentError
        ↓
AgentErrorPolicy 生成结构化决策
        ↓
AgentLoop 执行决策
        ↓
UI 展示安全信息，日志记录诊断信息
```

设计原则：

- 底层模块只负责识别和转换异常
- 策略层只负责决策，不直接操作 UI、Session 或工具
- AgentLoop 只负责执行决策，不判断具体错误类型
- 用户可见信息和内部诊断信息分离
- 默认优先恢复任务，避免无必要地终止 AgentLoop
- 所有异常路径都保留可测试的结构化结果

## 二、统一错误模型

新增独立错误模块，定义统一的 `AgentError`：

```text
AgentError
├── category
├── operation
├── retryable
├── user_message
├── model_message
└── cause
```

`category` 使用有限类别：

- `network`
- `timeout`
- `rate_limit`
- `authentication`
- `invalid_request`
- `tool_execution`
- `tool_permission`
- `session_persistence`
- `context_compaction`
- `internal`

`cause` 只用于内部日志，不进入模型上下文和 TUI

## 三、分层职责

### 1. 底层模块

- `ModelClient` 将供应商异常转换为模型相关的 `AgentError`
- `ToolManager` 将工具失败转换为安全的 `ToolResult`
- `SessionStore` 报告持久化异常，不决定 Agent 是否停止
- `ContextManager` 报告摘要异常，并提供规则兜底入口

底层模块不负责跨模块重试，也不直接修改 TUI 状态

### 2. AgentErrorPolicy

策略层接收 `AgentError`，返回结构化 `ErrorDecision`：

```text
ErrorDecision
├── action: retry | continue | fallback | stop
├── delay_seconds
├── max_attempts
└── visible_message
```

第一版策略集中写在策略表中，不开放动态配置：

| 错误类别 | 默认动作 | 次数 |
|---|---|---:|
| 网络错误 | 重试 | 1 |
| 超时 | 重试 | 1 |
| 限流 | 延迟后重试 | 1 |
| 认证错误 | 终止当前模型请求 | 0 |
| 参数错误 | 终止当前模型请求 | 0 |
| 工具业务错误 | 返回模型 | 0 |
| 工具执行器异常 | 返回模型 | 0 |
| Session 写入失败 | 后台重试并标记降级 | 2 |
| 上下文摘要失败 | 使用规则兜底 | 1 |

### 3. AgentLoop

AgentLoop 根据 `ErrorDecision` 执行动作：

- `retry`：重新发起当前模型请求
- `continue`：将结构化错误作为工具结果或消息继续交给模型
- `fallback`：调用上下文或持久化的兜底流程
- `stop`：结束本轮并返回已产生的结果

AgentLoop 不判断错误类别，也不生成用户提示文本

### 4. UI

UI 只消费安全展示信息：

- 显示当前请求失败或 Session 降级状态
- 保留已经生成的部分 assistant 回复
- 不展示密钥、完整堆栈、内部绝对路径和底层请求细节

## 四、模型请求失败

模型流式输出中断时，保留已经生成的 assistant 内容，并记录终止状态：

```text
assistant message
├── content: 已生成的部分内容
├── status: completed | cancelled | error
└── error_category: 可选错误类别
```

网络、超时和限流错误按策略表有限重试。认证和参数错误不重试

## 五、工具失败

工具失败默认不终止 AgentLoop：

```text
工具异常
    ↓
安全 ToolResult
    ↓
写入模型上下文
    ↓
模型决定下一步
```

工具结果分为两层：

- 模型可见：工具名、错误类别、可行动的错误说明
- 内部诊断：完整异常、堆栈和执行细节

工具权限拒绝、参数错误、文件不存在和执行器异常都通过错误工具结果反馈模型。只有 Agent 运行状态本身不可恢复时才终止 AgentLoop

## 六、Session 持久化失败

采用运行时优先、后台有序持久化：

```text
AgentLoop 产生消息
        ↓
先追加到运行时 Memory
        ↓
加入持久化队列
        ↓
后台顺序写入 JSONL
        ↓
成功：移出队列
失败：有限重试并标记 Session degraded
```

- 后续消息继续进入 Memory 和待写队列
- 消息必须按照产生顺序写入
- 退出前执行一次 `Flush`
- Flush 失败时提示用户部分消息未保存
- 不引入临时恢复文件

运行时状态和持久化状态必须分开统计：任务可以完成，但 Session 仍可能处于未完整保存状态

## 七、实现顺序

1. 新增统一错误模型和错误分类
2. 新增 `AgentErrorPolicy` 与策略表
3. 接入模型客户端错误转换和有限重试
4. 接入工具错误结果和安全信息分离
5. 扩展 assistant 消息以保存取消和异常状态
6. 实现 Session 持久化队列、有限重试和降级状态
7. 接入 AgentLoop，保持 UI 只负责展示
8. 为每类错误增加离线故障注入测试
9. 运行完整测试集并进行真实网络冒烟验证

## 八、验收标准

- 所有跨模块异常都能转换为统一 `AgentError`
- 错误策略集中在 `AgentErrorPolicy`
- AgentLoop 不包含按错误类别散落的分支
- 工具失败能够反馈模型并继续运行
- 模型中断能够保留部分 assistant 回复
- Session 写入失败不会静默丢失状态
- Session 最终失败时用户能看到降级提示
- 内部敏感信息不会进入模型上下文和 TUI
- 故障注入测试覆盖重试、继续、兜底、终止四类决策
