# 第六轮优化方案

## 总体判断

本次实现「slash command 基础设施 + skill 管理」两件事。先建命令基础设施，再以 `/start-skill`、`/stop-skill` 作为第一批命令实现 skill 的显式激活与注入。不实现渐进式披露、不建元数据列表、不做模型自主发现。

## 实施顺序

1. 新增 `src/core/commands/`：命令类型与注册表
2. 接入 `ui.py`：`handle_submit` 检测 `/` 前缀并分发
3. 新增 `src/core/skills/`：skill 扫描、frontmatter 解析、激活状态、内容注入
4. 实现 `/start-skill`：交互式勾选选择器
5. 实现 `/stop-skill`：展示已激活 skill 并取消
6. 单元测试 + 完整测试集 + 真实交互验证

## 架构分层

### 1. slash command 注册表（`src/core/commands/`）

```text
commands/
    __init__.py      # 导出注册表与默认命令集合
    registry.py      # SlashCommand 类型 + CommandRegistry
    start_skill.py   # /start-skill 处理器
    stop_skill.py    # /stop-skill 处理器
```

- `SlashCommand`：`name`、`description`、`handler(context)`
- `CommandRegistry`：`register` / `get` / `dispatch`
- `dispatch` 解析 `/<name> [args]`，命中则执行并返回 True，未命中返回 False

### 2. TUI 接入（`ui.py`）

- `handle_submit` 开头：`prompt.startswith("/")` → 交给注册表分发，命中则直接返回，不进入正常用户消息流程
- 交互式命令通过 `CommandContext` 拿到 screen、session、skill_manager 等依赖

### 3. skill 管理（`src/core/skills/`）

- skill 目录：项目级 `skills/<name>/SKILL.md`，frontmatter 只含 `name`、`description`
- `SkillManager`：`list()` / `activate(name)` / `deactivate(name)` / `active()`
- 注入：激活的 skill 内容 → 每轮追加为系统消息（追加在基础提示词之后）

### 4. 交互式选择器

- 复用 `SessionPicker` / `ApprovalPrompt` 的 prompt-toolkit 模式
- 上下键滚动、Space 切换 `[]`/`[√]`、Enter 确认

## 具体命令

| 命令 | 性质 | 行为 |
|---|---|---|
| `/start-skill` | 交互式 + 有状态 | 展示可用 skill，勾选激活，激活后每轮注入 |
| `/stop-skill` | 交互式 + 有状态 | 展示已激活 skill，取消后停止未来注入 |
| `/compact`（后续） | 动作式 | 手动触发 ContextManager 压缩 |
| `/model`、`/btw`、`/resume`（后续） | 待定 | 兄弟命令，走同一注册表 |

## 新增命令约定

新增一个 slash command 必须且只能：

1. 在 `commands/` 下新增一个处理器文件
2. 在注册表（或 `commands/__init__.py`）新增一行注册

不允许把命令逻辑散落到 `ui.py`、`session.py`、`agent_loop.py`。

## 测试计划

- `CommandRegistry`：注册、查找、重复注册拒绝、未知命令返回 False
- `handle_submit`：`/` 前缀分发命中、非命令走正常消息流程
- skill 扫描：发现 `skills/` 下的 skill、frontmatter 解析、无 frontmatter 容错
- 激活状态：activate / deactivate / active
- 注入：激活的 skill 内容出现在模型请求的系统消息中
- 选择器：上下键滚动、Space 勾选/取消、Enter 确认
- `/stop-skill`：取消后不再注入

## 验收标准

- 输入 `/start-skill` 显示可用 skill 并可勾选激活
- 激活后每轮模型请求携带该 skill 内容
- `/stop-skill` 展示已激活 skill 并可取消，取消后停止注入
- 未知命令给出提示，不进入正常消息流程
- 新增命令只改注册表一行 + 新增一个文件
- `uv run pytest` 全部通过
- 手动验证一次真实勾选与注入

## 明确不做

- 渐进式披露（元数据列表、模型自主发现）
- 选择器 type-to-search（仅上下键滚动，可后续增强）
- 激活状态跨会话持久化（重启即清空，会话级生命周期）
- skill frontmatter 丰富字段（只 `name`、`description`）
- 注入内容与基础提示词的冲突处理（简单追加）
- 用户级/全局 skill 目录（v1 只支持项目级 `skills/`）
