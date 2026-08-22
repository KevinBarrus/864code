# 第十一轮优化方案

## 总体判断

本轮是状态栏与列表样式的深度调整（对齐 Pi），外加 Markdown 换行修复、假复制修复和起始信息。参考 Pi 源码（footer.ts 整行渲染、select-list.ts 列对齐、user-message.ts Box、builtInHeader 起始信息）。按依赖顺序推进，每个子问题完成跑测试、提交。

## 建议执行顺序

1. **11.1 状态栏重构**（问题二/三/四/五/六/十三，布局基础）
2. **11.2 输入框前缀删除**（问题一，独立小改）
3. **11.3 列表去背景与列对齐**（问题九/十）
4. **11.4 用户消息 n+2 全灰**（问题十一）
5. **11.5 Markdown 换行修复 + 假复制修复**（问题十二/十四）
6. **11.6 起始信息：logo + 操作提示 + skill + Context 栏**（问题七/八）

## 问题二/三/四/五/六/十三：状态栏重构

- 状态栏改**整行字符串渲染**（对齐 Pi footer.ts）：行一 `pwdLine`、行二 `statsLine`，每行用 `{左侧内容} + " ".repeat(width - left宽 - right宽) + {右侧内容}` 手动右对齐
- 删除 `approval-area` 灰色背景（状态栏与底部面板统一无背景，落到终端默认背景）
- 全部字体 dim 淡灰（`#666666`，Pi dimGray）
- 目录 `format_cwd_for_footer`：home 目录 → `~`（复制 Pi formatCwdForFooter 逻辑）
- 信息行顺序：`↑{in} ↓{out} R{read} CH{hit}% ${cost} Balance:{balance} {percent}%/{window}(auto)`；自动压缩开启时末尾 `(auto)`
- 复制提示与模型信息因整行渲染自然右对齐

## 问题一：输入框前缀删除

- `_get_input_line_prefix`：去掉 `> ` 前缀，只保留左右留白

## 问题九/十：列表去背景与列对齐

- 底部区域（补全 CommandPicker、选择器、审批）删除 `approval-area` 背景
- CommandPicker 行排版对齐 Pi select-list：name 列宽 = 所有项 name 最大宽度 + GAP，description 左对齐、间距拉大

## 问题十一：用户消息 n+2 全灰

- 根因：外层 `_conversation_content` HSplit padding=1 插在用户消息的 3 个 Window 之间产生无背景间隔行
- 方案：用户消息改**单个 Window**，control 文本前后各加一个空行（`\n{content}\n`），全部带 `conversation-user` 背景 → 内容 n 行展示 n+2 行全灰

## 问题十二/十四：Markdown 换行 + 假复制

- `render_markdown`：行间插入 `("\n")` fragment，修复全部挤一行（表格/有序列表/分隔线随之正常）
- `ui.py` `on_copy` 回调：先 `copy_text_to_clipboard(text)` 再显示 5 秒提示

## 问题七/八：起始信息

- logo：`epsilon v{version}`（加粗 accent 色，Pi 风格）
- 操作提示：`c-d exit · / commands · Esc cancel · ↑/↓ select`（dim）
- 当前可用 skill 名称列表
- `[Context]` 栏（mdHeading 标题色）：内置 agent.md + 项目 AGENTS.md 路径（相对/`~` 缩写，dim）

## 测试计划

- 状态栏：整行右对齐、dim 样式、`~` 缩写、信息行顺序与 (auto)
- 列表：无背景、列对齐
- 用户消息：n+2 行全灰（无黑间隔行）
- Markdown：多行换行、有序列表、表格
- 复制：on_copy 写剪贴板
- 起始信息：logo/操作提示/skill/Context 栏渲染

## 验收标准

- 输入框无 `>` 前缀
- 状态栏无背景、淡灰、右对齐、`~` 缩写、信息行 + (auto)
- 列表无背景、name 列对齐
- 用户消息 n+2 行全灰
- Markdown 正常换行、有序列表/表格解析正确
- 拖选复制真实写入剪贴板
- 新建会话显示 logo + 操作提示 + skill + [Context] 栏
- `uv run pytest` 全部通过

## 明确不做

- W（cacheWrite）不显示（deepseek 无数据，Pi 实测也无）
- 状态栏颜色高亮区分（上下文超阈值变色等，Pi 有但暂不做）
