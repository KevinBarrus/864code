# 问题 6：skill 管理与 slash command 基础设施缺失

## 发现来源

本问题整理自与用户关于「epsilon 是否支持 skill、如何支持」的多轮设计讨论。讨论覆盖了渐进式披露、Pi 的元数据注入、Codex 的 `$` 显式调用、生命周期控制等方案，最终形成明确的取舍结论。用户明确表示：不为使用某个技术名词而使用该技术。

## 总体判断

epsilon 目前没有任何 skill 能力，也没有 slash command（`/` 开头命令）基础设施：

- `src/core/` 下没有命令注册表、没有命令分发、没有 skill 扫描/解析/注入模块
- `ui.py` 的 `handle_submit` 把所有输入都当作用户消息，无法识别 `/` 命令
- 上下文只能注入静态 `AGENT_SYSTEM_PROMPT` 和压缩摘要，无法注入用户激活的 skill

本次补齐两块能力，且**先建基础设施、再挂第一个业务**：

1. **slash command 基础设施**：独立、分层、可扩展的命令注册表，新增命令只需「一行注册 + 一个处理器文件」
2. **skill 管理**：以 `/start-skill`、`/stop-skill` 作为第一批命令，实现「用户显式激活 skill → 每轮注入其内容」

## 设计决策（来自讨论的取舍）

1. **不采用渐进式披露**：不做元数据列表进 system prompt、不做模型自主发现。理由：用户重视可控性，不想模型自作主张加载 skill；skill 的「约束残留」无法真正解除，模型自主加载会放大不可控
2. **采用用户显式激活 + 会话级生命周期**：用户通过 `/start-skill` 勾选激活，激活后每轮注入；`/stop-skill` 取消后停止未来注入
3. **接受软停止限制**：skill 内容一旦进入历史就会残留，`/stop-skill` 只能停止未来注入、不能擦除过去——这是所有「内容进上下文」系统的共同限制，设计上清醒接受
4. **slash command 是独立基础设施**：`/start-skill`、`/stop-skill`、`/model`、`/compact`、`/btw`、`/resume` 等均为注册表的兄弟命令；`/compact` 是手动触发已有的 ContextManager 压缩，不是新机制

## 现有代码缺口

- 无命令注册与分发（`CommandRegistry`）
- 无 `/` 前缀识别（`handle_submit` 直接处理所有输入）
- 无 skill 扫描、frontmatter 解析、激活状态、内容注入
- 无交互式勾选选择器（已有 `SessionPicker` / `ApprovalPrompt` 的 prompt-toolkit 模式可复用）

## 验收前提

新增一个 slash command 只能改动两处：注册表加一行、新增一个处理器文件。命令管理代码不允许散落到 `ui.py`、`session.py`、`agent_loop.py` 等模块。层次清晰、分层解耦、职责单一。
