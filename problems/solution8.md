# 第八轮优化方案

## 总体判断

修复 epsilon TUI 的交互与显示问题，按子问题逐个推进。参考 Codex 的补全、选择器与状态栏实现。

## 实施顺序（子问题）

### 8.1 补全交互（Enter 应用选中项、Tab 补全不执行、exact 优先、隐藏状态栏）

- `screen.py`：
  - submit 绑定：补全 active 时先应用 `current_completion`（无则第一项）再提交，避免 `/mod` 直接提交原文本
  - 新增 Tab 绑定（补全 active 时）：应用当前补全但不提交
  - 状态栏包 `ConditionalContainer(filter=补全不活跃)`：补全展开时隐藏状态栏，收起恢复
- `SlashCommandCompleter`：匹配改为 exact 优先 + prefix 匹配（对齐 Codex），大小写不敏感
- 实测验证：`/mod` 删字符成 `/mo` 后补全仍持续匹配

### 8.2 选择器滚动 wrap 循环

- `choice_picker.py`：光标移动到边界后再移动 wrap 回另一端；滚动跟随保持
- `skill_picker.py`：同样改为 wrap 循环

### 8.3 主题颜色

- `theme.py`：`approval-selected` 从金色改为 `fg:ansibrightcyan`（亮青，对齐 Codex 的 cyan）

### 8.4 /model 切换反馈

- `commands/model.py`：切换/新建配置成功后，在**对话区**追加英文 tool 消息 `Switched to model: X`，不再走状态栏
- 状态栏模型名动态化：`StatusInfo` 或状态栏渲染改为读取当前运行时配置，切换模型后同步更新

### 8.5 余额查询

- `balance.py`：新增 DeepSeek 余额查询实现，调用 `GET {base_url}/user/balance`（Bearer API key），返回余额文本
- 查询失败或非 DeepSeek 端点时降级为「不可查询」状态（英文）
- `main.py`：启动时用真实实现替换 `UnavailableBalanceProvider`

### 8.6 UI 英文化

- 状态栏：`Model` / `Balance` / `Working directory`
- 命令提示：`Unknown command`、`Current config`、`Switched to model`、`No skills available`、`Activated skills`、`Stopped skills` 等
- 首次引导界面、配置错误提示、余额降级文案全部英文
- 代码注释保持中文

## 测试计划

- 补全：exact 优先排序、prefix 持续匹配、Enter 应用选中项、Tab 补全不提交
- 选择器：wrap 循环滚动、滚动跟随
- 状态栏：补全展开隐藏、收起恢复、模型名随切换更新
- 余额：mock HTTP 成功/失败路径
- 英文化：关键文案断言

## 验收标准

- 补全展开时状态栏隐藏，收起后恢复
- `/mod` Enter 直接执行 `/model`；Tab 补全不执行
- 选择器 wrap 循环滚动
- 选中项亮青色
- 切换模型后对话区英文提示、状态栏模型名更新
- 余额真实查询，失败降级
- 所有用户可见文本为英文
- `uv run pytest` 全部通过

## 明确不做

- 补全菜单的下移方案（pi 风格），采用 codex 的隐藏状态栏方案
- 命令描述的多列布局与匹配高亮（prompt_toolkit 补全菜单自带）
