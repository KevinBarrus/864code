# 问题 2：第二轮系统评价（压缩 / 评测 / 记忆 / 工具 / TUI）

## 发现来源

本问题整理自一次对当前项目的整体评价，核对范围包括 `src/core`（`context.py`、`session.py`、`session_store.py`、`session_persistence.py`、`agent_loop.py`、`openai_client.py`、`memory.py`、`ui.py`、`screen.py`、`tool_approval.py` 等）、`src/core/tools`、`evaluation`、`design` 与 `tests`。

## 总体判断

这是一个结构清晰、边界划分明确的 Python Coding Agent Runtime：Session/Turn/Step 分层、JSONL 事件持久化、独立的 ContextManager / ToolManager / PermissionManager、离线+在线双层评测，代码可读性和可测试性（204 个测试）都很好。作为「面试可讲清楚」的项目是达标的。

但按**生产级**标准，存在几类系统性问题，按影响排序：

- **最致命**：Token 估算对中文严重失真，直接击穿压缩保护 → 超窗后 API 报 400/422 被当作「不可重试」硬停。
- **安全问题**：工具审批看不到参数 + 会话级按「工具名」授权，`run_command` 一次授权后任意命令静默执行。
- **评测问题**：离线是脚本化冒烟、在线单任务太弱、样本量 6 无统计意义、baseline 门禁阈值对噪声敏感。
- **工程问题**：上下文预算只在请求前查一次、摘要请求输入无上限、TUI 每个 token 全量重建、`list_sessions` 全量读文件等。

## 一、上下文压缩策略

### 问题一：Token 估算 `chars/4` 对中文严重低估（最核心缺陷）

`context.py:583-594` 的 `estimate_message_tokens` 用 `ceil(chars / 4)`。这个公式对英文（约 4 字符/token）勉强可用，但对中文约 1 字符 ≈ 1+ token（DeepSeek 类 BPE 下中文常是 0.5~1 字符/token），**低估 4~6 倍**。而本项目是纯中文项目。

后果是连锁的：

1. `ContextManager.build()` 认为没超预算，**不触发压缩**；
2. 真实请求超出模型窗口，API 返回 400/422；
3. `_to_model_error`（`openai_client.py:114`）把 `BadRequestError`/`UnprocessableEntityError` 归为 `invalid_request`，`error_policy.py:27` 定义为 `stop`（不重试）；
4. 于是整个 turn **硬失败**，压缩兜底完全失效。

> 也就是说：估算失真 → 压缩不触发 → 超窗 → 错误分类为不可恢复 → 崩溃。这是当前系统最脆弱的一环。生产级做法是接入真实 tokenizer（`tiktoken` 或目标模型的 tokenizer），至少按语言区分（CJK 按 1 字符≈1 token，ASCII 按 /4），并把 400/422 的「context length」错误单独识别为可恢复、触发压缩。

### 问题二：上下文预算只在请求前检查一次，工具轮内不再校验

`ui.py:82` 只在 `agent_loop.run()` 之前调用一次 `build_for_model_result`。`AgentLoop.run`（`agent_loop.py:82-126`）内部每轮工具结果直接 `context.append()`，**从不重新检查预算**。`max_tool_rounds=10` 只是轮次上限，不是 token 上限。一轮里 10 次工具调用，每次工具输出上限 16KB（≈4K token 估算），加上模型回复，很容易在中途把窗口顶爆，且没有中途压缩的机会。

生产级应在每次工具结果写回后重估，超限就在 turn 内触发压缩或截断。

### 问题三：摘要请求的输入没有预算上限

`generate_context_summary`（`context.py:522`）把被压缩的旧消息**完整序列化**（`_serialize_messages`，含完整工具参数）后发给**同一个模型**做摘要，没有对摘要输入做任何截断。`design/context.md:84` 明确写了「工具结果在摘要请求中允许使用较短版本，避免摘要请求本身过大」，但代码没有实现。当历史非常大时，摘要请求本身就会超窗失败，然后只能回退到规则裁剪。

### 问题四：压缩失败时 `add_compaction` 返回值被忽略，状态会漂移

`ui.py:87-88`：

```python
if context_result.compaction is not None:
    session.add_compaction(context_result.compaction)
```

`Session.add_compaction`（`session.py:78`）在 `flush()` 失败时直接 `return False`、**不写入运行时 `_compactions`**。后果：本轮模型已经看到了压缩后的上下文，但会话里没有记录这条压缩 → 下一轮 `get_compactions()` 拿不到 → 从完整历史**重新摘要**，产生一份可能不同的摘要。不是 correctness bug，但是一致性和效率问题（重复摘要 + 状态漂移）。返回值应被处理（至少降级提示）。

### 问题五：边界拆分的兜底可能产出「孤立 tool result」

`_split_oversized_latest_turn`（`context.py:491`）循环内每次都校验 `_has_valid_tool_chain(suffix)`，但**兜底 `return latest_group[:-1], latest_group[-1:]` 不校验**。若最后一组末尾恰好是 `tool` 消息、且它前面没有能凑成完整链的边界，兜底会留下一个没有对应 `assistant tool_call` 的 `tool` 消息，发给 API 可能被拒。

`_fit_messages_to_budget`（`context.py:395`）也有类似问题：当只剩一个 group 时，它删除/截断**最后一条**消息，若那是 `tool` 消息，前面的 `assistant tool_call` 就悬空了。虽然都在 fallback 路径，但设计验收标准（`context.md:296-299`）明确要求「保留的工具调用链结构有效」。

## 二、评测方式

### 问题六：离线场景是「脚本化冒烟测试」，不是能力评测

`scenarios.py` 里每个场景都用 `FakeModelClient` 返回**硬编码**的事件序列（如 `run_tool_recovery_scenario` 里预先写好「先失败调用、再修正调用、再回复」）。因此：

- `tool_recovery_rate`、`task_completion_rate` 衡量的不是「模型能否恢复」，而是「pipeline 是否按固定脚本跑通」；
- 断言如 `final_content == "已根据工具错误修正路径并完成读取"`（`scenarios.py:294`）是**验证假客户端回显了自己的预设文本**，等价于测试自己在测自己。

这本身不算错（design 里也声明「核心链路回归用于验证模块协作，真实任务评测才用于衡量模型能力」），但**报告把所有指标混在一张表里**（`report.py`），读者无法分辨哪些数字来自脚本、哪些来自真实模型。

### 问题七：在线评测任务太弱，且断言不验证「顺序/质量」

`online.py:194` 的在线任务只是「读 note.txt → 把 before 改成 after → 说完成」。断言（`online.py:218-239`）：

- `file-content` 是好的 ground-truth；
- 但 `tool-chain` 只检查 `"read_file" in tool_names and "edit_file" in tool_names`——**不验证先读后改的顺序**；
- 没有对最终 assistant 回复内容做任何 judge/质量评分（design 里 `judge_score` 接口预留了但没用）。

结果：一个「盲目调用 edit_file 而不理解任务」的模型也能通过。**单任务、无难度梯度、无负样本、无质量评分**，这个在线评测几乎不能区分好 agent 和坏 agent，只能证明「链路能跑」。

### 问题八：样本量 6，P50/P95 无统计意义，且无 CI 门禁

`online.py:459` 默认重复 6 次。design（`evaluation.md:184`）自己也写了「样本量小于 5 时只展示观察值，不宣称统计稳定性」，6 次只是勉强过线。P95 在 6 个样本下本质就是「最大值」。没有置信区间、没有显著性检验（design 声明不做，可接受），但报告里把 P95 当作核心指标卡片展示，容易被误读。

### 问题九：baseline 门禁阈值对噪声敏感，会 flaky

`baseline.py:10-11` 用 `MAX_P95_DURATION_RATIO = 1.25`、`MAX_AVERAGE_MODEL_REQUEST_RATIO = 1.25`，并且 `total_compactions` **只要增加就判回归**（`baseline.py:179-184`）。在 6 个样本、网络延迟主导的在线评测里，P95 或平均请求数波动 25% 是常态；一次合法的改动多触发一次压缩就会直接红门禁。这些阈值缺少噪声缓冲（如基于标准差或最小样本量）。

### 问题十：报告只显示每条结果的第一个失败断言

`report.py:113-121` 的 `_failure_row` 用 `next(assertion for assertion in result.assertions if not assertion.passed)`，一条结果有多个断言失败时**只显示第一个**，其余被隐藏。调试价值受损。

### 问题十一：`estimated_tokens` 用同一套失真启发式，报告里的 Token 不可比

`metrics` 和报告里的 `estimated_tokens` 全是 `chars/4` 估算。design 要求「实际 Token 不可用时明确标记 null，不能用估算冒充」，`actual_tokens` 确实是 null（这点做对了），但 `estimated_tokens` 仍被当作一个「指标」和耗时并列展示，且数字系统性偏低，容易误导。

## 三、记忆管理

### 问题十二：运行期 Memory 全量驻留 + 每轮全量拷贝，O(n²)

`Session.get_messages()`（`session.py:68-71`）→ `Memory.get_messages()` 每轮返回 `list(self._messages)` 完整拷贝；`ContextManager.build_for_model_result` 又 `list(messages)` 再拷贝。压缩只减小「发给模型」的视图，**不减小运行时 Memory 和 JSONL**。长会话下：内存无界增长 + 每轮 O(n) 拷贝 + 累计 O(n²)。

### 问题十三：`list_sessions` 为取一个标题而全量解析每个文件

`session_store.py:132-158`：`list_sessions` 对每个 `.jsonl` 调 `load_messages`，而 `load_messages` 逐行解析**整个文件**，只为取第一条 user 消息当标题（`_create_title`）。会话多、历史大时，列会话的开销是 `O(总历史大小)`。生产级应只读首行、或维护一个 title/mtime 的 sidecar 索引。

### 问题十四：无跨会话长期记忆（设计上延期，但对「生产级」是明确短板）

`memory.py` 只是一个 list 包装。跨会话的经验、反思、用户偏好、项目长期上下文完全没有。design 里明确把它放到后续阶段，作为 v1 可接受；但按「生产级」要求，这是和 Claude Code / Codex 拉开差距的核心能力，值得在 roadmap 里给它更高的优先级。

## 四、工具管理

### 问题十五：工具审批不显示参数（安全 + 可用性缺陷）

`tool_approval.py:75-87` 的 `_render` 只渲染 `Allow tool {name}?` 和三个选项，**完全不渲染 `tool_call.arguments`**。对 `run_command`，用户被问「允许 run_command 吗？」却看不到将要执行的命令；对 `write_file`/`edit_file`，看不到路径和内容。审批的核心目的就是「review 要做什么」，这个信息缺失让审批形同虚设。

### 问题十六：会话级授权按「工具名」粒度，`run_command` 一次授权后全放行

`permissions.py:56-66`：`ALLOW_SESSION` 的 grant 键是 `(source, name)`。结合上一条：用户批准一次 `run_command`（比如 `git status`），**之后整个会话所有命令**（包括 `rm -rf /`）都静默执行，不再展示、不再确认。对「每次都要确认」的命令类工具，按工具名授权是错误粒度——应按「命令前缀/具体命令」授权，或命令工具永远不提供 session 级授权。

### 问题十七：MCP 已实现但未接入 CLI（死代码）

`tools/mcp.py`、`tools/mcp_stdio.py`、`ToolManager.register_mcp_provider` 都实现并有测试，但 grep 确认 `run_chat`/`main.py` 从未调用 `register_mcp_provider` 或构造 `StdioMcpProvider`。MCP 目前是「测试可达、产品不可达」的功能。对面试展示是减分项——讲解时说「支持 MCP」但实际跑起来接不上。

### 问题十八：文档与代码不一致：工具输出截断

`design/tool.md:23` 写「当前阶段不做工具输出截断」，`tool.md:317` 又把它列进「暂不实现」；但 `output_limits.py` 已实现并在 `file_tools.py`/`command_tool.py` 应用了 16KB/400 行截断。文档是你要用来准备面试讲解的，这类漂移会导致讲解与代码对不上。

### 问题十九：`read_file` 先全量读入再截断 / `search_files` 无界递归

- `file_tools.py:21`：`read_file` 先 `read_text` 读整个文件再截断，超大文件会先占满内存。
- `file_tools.py:88`：`search_files` 用 `root.rglob("*")` 遍历**所有文件**做子串匹配，没有 `.gitignore`/隐藏目录/二进制文件/符号链接/文件大小上限。在这个项目本身（含 `.git`、`uv.lock`）上跑一次全库搜索就会很慢，真实大仓库可能卡死或触发符号链接循环。生产级至少要有：跳过 `.git`/`node_modules` 等、二进制探测、`os.walk` + 逐目录剪枝、单文件大小上限、总遍历超时。

### 问题二十：`run_command` 无沙箱 + 用 `create_subprocess_shell`

`command_tool.py:27` 用 `create_subprocess_shell`（等价 `shell=True`），命令可直接访问工作区外的任意位置。design 承认这是 v1 限制，但结合问题十五、问题十六的授权粒度问题，风险被放大。生产级至少要把「工作区路径校验」和「命令白名单/沙箱」补上。

## 五、TUI

### 问题二十一：每个 token 全量重建整个对话视图，流式输出 O(n²)

`screen.py:390-412`：`_sync_conversation_view` 每次被调用都**重建所有 `Window` children**，而 `append_to_entry`（`screen.py:128`）在**每一个 `TextDelta`** 上都调用它。流式输出 n 个 token 时是 O(n²) 的窗口重建 + invalidate。会话稍长（几百条消息）后，长回复会明显卡顿、抖动。生产级应只更新当前 entry 的控件内容，而不是重建整个 HSplit。

### 问题二十二：无输入历史、无 Markdown/代码高亮

- `screen.py:78` 的 `TextArea` 没有挂 `prompt_toolkit.history.History`，上箭头无法召回历史输入；
- 对话区是纯文本 `FormattedTextControl`，代码块无语法高亮、无 Markdown 渲染。

对一个 coding agent，代码高亮和输入历史是「够用」级别的门槛，而不是加分项。

### 问题二十三：恢复历史时一次性 `add_entry`，长历史恢复慢

`ui.py:160-164` 恢复时逐条 `add_entry`，每条都会触发 `_sync_conversation_view` 全量重建（见问题二十一），恢复一个几千条消息的会话会非常慢。应支持批量构建后再一次性 invalidate。

## 六、其他系统性问题

### 问题二十四：错误重试策略粗糙：无退避、不读 Retry-After

`error_policy.py:24`：`rate_limit` 固定 `delay_seconds=1`、重试 1 次；`network`/`timeout` 重试 1 次**无退避**。生产级应：指数退避 + 抖动 + 读取 `Retry-After` 头 + 对 429 做更长等待。

### 问题二十五：模型流式请求无显式超时

`openai_client.py:57-95` 的 `stream_response` 没有设置请求超时，也没有 `max_tokens`。`run_command` 有 60s 超时，模型请求却没有。连接挂起（半开连接）会**无限期挂死 agent loop**，只能靠用户 Ctrl+C。生产级至少要有 per-request 超时和整体 turn 超时。

### 问题二十六：无系统提示词（system prompt）

grep 确认：整个 agent **没有任何基础 system prompt**，唯一 `role="system"` 的消息是压缩摘要和 fallback 提示。模型拿到的只有原始对话 + 工具定义。对于一个 coding agent，缺少「你是谁、如何使用工具、安全约束、工作习惯」的角色指令是显著缺失——模型行为完全靠工具 description 引导。design 文档里也没有规划这一块。

### 问题二十七：`main.py` 无兜底异常捕获

`main.py:57-72` 只捕获 `ConfigError`、`SessionStoreError`、`KeyboardInterrupt`。任何其他运行时异常（prompt_toolkit 错误、`ContextBudget` 的 `ValueError`、意外的 `OSError`）都会裸 traceback 崩溃。生产级应有顶层 catch + 干净提示 + 非零退出码。

### 问题二十八：`run_command` 超时后未回收 stdout 缓冲

`command_tool.py:39-46`：超时后 kill 进程组，但没有 `process.communicate()` 去排空管道。如果命令写满 stdout 管道后卡住，`_stop_process_group` 之后残留的子进程可能仍然持有管道写端，属于小概率的资源泄漏点。影响不大，可顺带加固。

## 优先级建议

1. **P0（安全 + 正确性）**：问题一 Token 估算 + 问题二十五超时 + 问题十五/问题十六审批安全 —— 这是「能用且不闯祸」的底线。
2. **P1（系统健壮性）**：问题二轮内预算、问题三摘要输入上限、问题二十四/问题二十五重试与超时、问题二十六系统提示词。
3. **P1（评测可信度）**：问题六/问题七评测任务太弱、问题八/问题九样本量与门禁阈值、问题十报告只显示首个失败。
4. **P2（性能与体验）**：问题二十一 TUI O(n²)、问题十三 `list_sessions` 全量读、问题十二内存 O(n²)、问题十九 search_files 无界。
5. **P2（完整度）**：问题十七 MCP 未接线、问题十八文档漂移、问题十四长期记忆。
