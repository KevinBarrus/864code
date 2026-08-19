# 问题 5：第三轮系统评价（生产级 / 大厂面试水准）

## 发现来源

本问题整理自对当前项目的第三次整体评价。核对范围：`src/core` 全部源码（`context.py`、`session.py`、`session_store.py`、`session_persistence.py`、`agent_loop.py`、`openai_client.py`、`errors.py`、`error_policy.py`、`memory.py`、`balance.py`、`ui.py`、`screen.py`、`conversation_view.py`、`tool_approval.py`、`session_picker.py` 等）、`src/core/tools`、`evaluation`、`design` 九份设计文档与 `tests`。本轮聚焦八个方向：上下文管理、压缩策略、后端工程、系统设计、评测方案、记忆管理、Agent Harness、前端界面。

与 `problem2.md`（28 条）、`problem3.md`（4 条）、`problem4.md`（2 条）不同，本轮是在前四轮修复之后，按「生产级水准」与「头部大厂 Agent 面试水准」两条线重新打分。多数早期问题已修复，下列问题均为**当前仍存在**的残留项；其中标注「（明确推迟）」的是设计文档里主动声明暂不做的边界，不算回归，但在生产级口径下仍计为差距。

## 总体判断

- **生产级：工程内核达标，产品完整度未达标。** 错误模型（`errors.py`/`error_policy.py`）、可恢复持久化（`session_persistence.py`/`session_store.py`）、上下文压缩（`context.py`）、分层评测（`evaluation/`）四块是真正的生产级；但 tokenizer、Token 用量遥测、命令沙箱、代码正确性评测、Markdown TUI 五块是明确留白的非生产边界。
- **大厂面试水准：达标，且是强信号。** 分层与依赖单向、`Protocol` 抽象、统一错误分类学、压缩的累计摘要与工具链完整性、评测的 baseline 回归与样本量门控、以及「写清楚为什么不做」的设计文档，都是区分度所在。最值钱的是**每个边界都想清楚并落进了文档**。

一句话：这是一个「生产级纪律 + 文档化非生产边界」的 v1 内核，不是「生产级产品」。

## 一、系统设计

### 问题一：Turn / Step 分层只存在于文档，代码没有对应对象

`design/architecture.md:68-101` 明确描述了 `Session → Turn → Step` 三层，且 `Session` 应「负责保存当前运行状态、Token 使用量、当前是否存在活动 Turn」。但代码里没有 `Turn`、`Step` 任何类；`agent_loop.run()` 一个函数把一轮的所有状态（`text_parts`、`tool_calls`、`new_messages`）都堆在局部变量里（`agent_loop.py:75-158`）。`Session` 也只存消息 + 压缩记录（`session.py:20-23`），没有文档承诺的运行状态与 Token 用量。

后果：取消、错误、预算、完成状态没有归位边界，重试/恢复的粒度只能到「整个 loop」，无法到单 Step。面试会被直接追问「你的 Turn 抽象在哪」，标准答案是「为保持 loop 简单刻意推迟」，但当前没有任何显式边界承接，属于「架构图领先实现」的 gap。

### 问题二：Session 未实现文档承诺的状态字段

`design/architecture.md:75-79` 列出的 Session 职责（模型配置、权限配置、当前运行状态、Token 使用量、活动 Turn 标记）里，实际 `Session`（`session.py:12-30`）只实现了 `session_id`、`workspace`、消息与压缩记录。权限配置由 `ToolManager` 持有、模型配置由 `Settings` 持有，运行状态与 Token 用量无处可查。跨进程恢复时「上次跑到哪、用了多少 Token」是不可知的。

## 二、后端工程

### 问题三：无 Token 用量遥测，`actual_tokens` 是死管道

评测模型里有 `actual_tokens` 字段（`evaluation/models.py:42`），报告里也区分「估算 / 实际」Token（`evaluation/report.py:151`），但 `openai_client.py` 的请求既没有 `stream_options={"include_usage": True}`，也不读取 `chunk.usage`（`openai_client.py:71-77`、`100-121`）。所以 `actual_tokens` 在运行时**永远为 `None`**，报告里永远是留空。

后果：`design/architecture.md:140` 说 Model Client 要「记录 Token 使用量和请求元数据」，没落地；估算误差也没有真实 usage 来校准。这是「管道铺好了但没接水」。

### 问题四：每条消息 `fsync`，无 group-commit

`session_store.py:221` 对每次 append 都 `os.fsync(file.fileno())`。chat 场景没问题，但 Agent 一个 turn 会产生数十条 tool/assistant 消息，等于几十次强制落盘。耐久性是对的，吞吐与写放大是代价，且没有批量/组提交。不是 bug，是耐久性↔吞吐的取舍，需说清。

### 问题五：消息加载整文件读入内存

`load_messages` / `load_compactions` 都走 `_read_records`（`session_store.py:224-242`），内部 `path.read_text().splitlines()` 把整个 JSONL 一次性读进内存。只有会话列表的标题读取做了流式（`_read_title`，`session_store.py:160-189`）。长会话恢复时会有内存尖峰。

### 问题六：无文件锁 / 并发写保护

两个进程同时打开同一个 session，JSONL append 会交错损坏。单用户 TUI 可接受，但生产级（后台 agent、多端恢复）需要显式锁或写时校验。

## 三、上下文管理与压缩策略

### 问题七：字符 token 估算对代码系统性低估，无真实 tokenizer

`estimate_text_tokens`（`context.py:701-705`）CJK 按 1 token、ASCII 按 `/4`。中文已修正（`_is_wide_character`，`context.py:708-721`），但**代码 token 密度远高于 4 字符/token**，ASCII 分支仍会低估 2~4 倍。`_is_wide_character` 的字符范围是手写的，会随目标 tokenizer 词表漂移。

现在有安全网兜底（`context_overflow` 结构化错误码 → `force_compaction` 重试，`agent_loop.py:92-113`），所以不会静默爆窗；但会**过早压缩或被迫二次压缩**。生产级应上 `tiktoken` 或目标模型 tokenizer，至少用服务端 `prompt_tokens` 校准。

### 问题八：摘要结构化校验靠 5 个标题字面匹配，脆弱

`_is_structured_summary`（`context.py:682-685`）要求 `## Goal / ## Progress / ## Key Decisions / ## Next Steps / ## Critical Context` 五个字面标题**全部**出现在摘要里。模型换个写法（如 `## 目标`、漏一个空行）就判定失败 → 重试 → 规则裁剪。有兜底所以不致命，但白白丢一次摘要调用，且与提示词的强耦合没有容错。

### 问题九：越预算的每个 turn 都重生成摘要，成本线性累积

`build_for_model_result`（`context.py:181-308`）每次从最新 compaction 重推上下文，只要仍越预算就**再发起一次摘要模型调用**。这是累计摘要设计（`design/context.md:199-214`）的有意行为——每轮新增旧消息都要并入摘要——但长期越预算任务 = 每 turn 多一次摘要请求，成本随 turn 数线性增长，无缓存/增量策略。

### 问题十：摘要输入预算 `// 2` 是拍脑袋启发式

`_summary_input_budget`（`context.py:118-122`）用 `_message_budget // 2` 作为摘要请求的独立输入预算，没有任何推导依据。它保证了摘要请求不超窗（有 `_limit_summary_source` 兜底），但「一半」这个系数是纯经验值。

## 四、Agent Harness

### 问题十一：工具串行执行，无并行

`agent_loop.run` 里多个 tool call 逐个 `await self._tool_manager.execute(...)`（`agent_loop.py:133-143`）。对「读两个无关文件」「并行跑多个测试」这类天然并行的调用，串行是能力与延迟的双重损失。生产级 agent（Claude Code、Codex）都会对无依赖的工具调用并行执行。

### 问题十二：无 turn 级总预算

只有单请求超时（first-byte / idle，`openai_client.py:100-121`）+ `max_tool_rounds` 轮次上限。没有总 wall-clock 预算、总 token 预算、总成本上限。一个模型持续要求工具调用的失控循环，只能靠 `max_tool_rounds=10` 硬兜底，没有「本 turn 已用 X token / Y 秒」的软限制。

### 问题十三：`max_tool_rounds` 硬编码，不进 Settings

`AgentLoop.__init__` 默认 `max_tool_rounds=10`（`agent_loop.py:66`），且 `ui.py:189` 构造时未传参。这个上限与 `context_window` 等预算同属运行时策略，却不走配置，无法按模型/任务调节。

## 五、记忆管理

### 问题十四：`memory.py` 只是 list 包装，不是「记忆管理」

`memory.py` 全文 32 行，就是 `list[Message]` + 返回副本（`memory.py:29-32`）。无跨会话记忆、无检索、无语义记忆、无「任务后反思写入记忆」。它只完成了 `design/memory.md` 的阶段一（进程内单会话），按「记忆管理」这个名字评判生产级是不达标的。名字要往小说，边界要往清说。

### 问题十五：内存无界增长 + 全量浅拷贝，长会话 O(n²)（明确推迟）

`Memory._messages` 永远 append，压缩只发生在 context-build 时（不改内存）。`get_messages()` 每次 `list(self._messages)` 全量拷贝（`memory.py:29-32`），`build_for_model_result` 里又 `list(messages)` 一层（`context.py:190`）。超长会话下这是重复拷贝叠加，之前标注过、仍未修。

### 问题十六：`balance.py` 是 stub

`UnavailableBalanceProvider.get_balance()` 恒返回「暂不可查询」（`balance.py:13-19`），`main.py:47` 用它填充状态栏。无任何真实余额查询实现，状态栏的「余额」永远是占位文本。

## 六、评测方案

### 问题十七：无代码正确性评测，测不出「代码对不对」

三个在线任务（`online.py:59-109`）全是「改文件内容 + 回复关键词」，衡量的是「工具链能否跑通」，**不是「生成的代码是否正确」**。头部大厂 coding agent 的黄金标准是「生成的代码跑通单测」（SWE-bench 风格），这里完全没有。`design/evaluation.md:131` 预留的 `judge_score` 也没实现。

### 问题十八：质量靠关键词子串，无 judge 评分

`_contains_keywords`（`online.py:444-447`）用 `keyword.casefold() in content` 判断最终回复。一个胡说的回复只要带上「note.txt」和「完成」就通过。没有模型评分，无法区分「真理解了任务」和「蒙对了关键词」。

### 问题十九：在线任务少且易，无真编码任务

3 个任务全是小文件替换，无「写函数 / 修 bug / 过测试」类真编码任务，无难度梯度，无负样本。这套在线评测几乎不能区分好 agent 和坏 agent，只能证明链路能跑。

### 问题二十：`task_completion_rate` 回归无样本量门控，门控不对称

`baseline.py:178-181` 对「任务成功率下降」的回归判断**不检查样本量**，而 P95 和平均请求数两条都经 `_has_stable_performance_samples`（`baseline.py:205-214`，要求 ≥20 样本）门控。n<20 时，一次偶然失败也会报「任务成功率下降」回归，与其余指标的门控策略不一致。

## 七、前端界面（TUI）

### 问题二十一：无 Markdown / 语法高亮

对话区纯文本（`FormattedTextControl(content)`，`screen.py:151-155`），代码块、列表、加粗都不渲染。coding agent 的 TUI 不能渲染代码块，是产品级最大的 UX 差（对比 Claude Code / Codex）。设计明确推迟「完整 TUI」。

### 问题二十二：键盘无法滚动历史

`ConversationView.scroll_by`（`conversation_view.py:57-67`）只被鼠标滚轮调用（`handle_mouse_event`，`conversation_view.py:69-75`）。`screen.py` 的 key bindings（`screen.py:293-379`）里**没有 PgUp/PgDn**。终端键盘优先用户无法滚动长对话，只能靠鼠标滚轮。

### 问题二十三：工具活动单行摘要，无展开查看

工具活动被压缩成 60 字符单行（`_tool_call_summary` / `_single_line`，`ui.py:204-248`），无展开/折叠查看完整工具输出。对「看命令实际输出了什么」这类调试诉求，信息被截断后无法就地查看。

## 八、安全（工具管理）

### 问题二十四：`run_command` 用 `shell=True` 且无沙箱，靠人肉审批

`create_subprocess_shell` + `start_new_session=True`（`command_tool.py:27-32`）。`shell=True` 有注入面，且无命令 allowlist/denylist、无网络 egress 控制、无沙箱。当前防线是「命令权限逐次人工审批 + 审批展示完整命令」（`permissions.py:63` 禁止会话级授权、`tool_approval.py:104-109` 展示 Command）。这是人肉沙箱，不是技术沙箱。设计明确推迟沙箱，但在生产级口径下，这是唯一的高危面。
