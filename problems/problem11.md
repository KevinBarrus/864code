# 问题 11：状态栏重构、列表去背景、用户消息布局、Markdown 修复与起始信息

## 发现来源

用户实际使用 TUI 后反馈的 14 个问题，参考 Pi 源码（footer.ts、select-list.ts、user-message.ts、Box、builtInHeader 等）对齐方案。

## 问题一：输入框前缀残留

输入区已改用上下水平线框（Pi 风格），但输入文字前仍有 `> ` 前缀，应删除（保留左右留白）。

## 问题二：状态栏灰色背景

状态栏（底部区域）仍有灰色背景（`approval-area` bg:#303030），应删除，让状态栏字体直接落在命令行窗口默认背景上（Pi footer 无背景）。

## 问题三：模型信息未右对齐

模型信息（厂商名·模型名·推理强度）没有位于状态栏最右侧。Pi 用整行字符串手动空格填充实现右对齐，epsilon 当前的 VSplit 方案未生效。

## 问题四：状态栏字体颜色

状态栏字体应像 Pi 一样使用淡灰色（dim，#666666）。

## 问题五：当前目录冗长

状态栏显示 `/home/kevinbarrus/projects/epsilon`，应像 Pi 一样把 home 目录缩写为 `~`（`~/projects/epsilon`）。

## 问题六：上下文信息顺序

信息行顺序应为：`↑in ↓out R{命中} CH{命中率}% ${cost} Balance {percent}%/{window} (auto)`，支持自动压缩时末尾加 `(auto)`。R 无 W（Pi 实测仅显示 R + CH，deepseek 无 cacheWrite 数据）。

## 问题七：新建会话不显示 logo

新建会话应先显示 logo（`epsilon v{version}`，Pi 风格加粗 accent 色）。

## 问题八：缺少前置信息

新建会话除 logo 外还应展示：基本操作提示（快捷键）、当前可用 skill、`[Context]` 栏（上下文文件列表，参考 Pi builtInHeader）。

## 问题九：补全列表灰色背景

输入 `/` 后下方列表仍有灰色背景，应像 Pi 一样字体直接落在命令行窗口默认背景。

## 问题十：列表文字对齐

列表行 name + description 展示：description 应左对齐，name 与 description 之间空格要拉大（Pi 按 name 列最大宽度 + GAP 对齐）。

## 问题十一：用户消息布局错乱

用户消息内容 n 行时展示为 n+2 行（首尾各 1 行灰色留白），且**全部背景统一灰色**。当前实现 1 行内容展示 5 行且灰黑相间——根因是外层 HSplit 的 padding=1 插在留白与消息之间，产生无背景的间隔行。

## 问题十二：Markdown 解析错误

回答全部挤在一行（无法换行）、有序列表（1 2 3 点）未解析、表格未解析、分点前出现一长条分隔线。根因：`render_markdown` 生成的 fragments 行间缺少 `\n`，所有行被拼接成一行。

## 问题十三：复制提示未右对齐

复制提示（`Copied N chars to clipboard`）没有位于右侧，且应与模型信息对齐。

## 问题十四：假复制

选中松开后显示复制提示但剪贴板无内容。根因：`on_copy` 回调只设置提示状态，未调用 `copy_text_to_clipboard`。

## 现有代码缺口

- `screen.py`：`_get_input_line_prefix` 的 `>` 前缀、状态栏 VSplit 布局、`approval-area` 背景、用户消息 3 Window + 外层 padding 间隔
- `markdown.py`：fragments 缺 `\n`
- `ui.py`：`on_copy` 未写剪贴板
- 无 logo / 起始信息 / Context 栏
- `command_picker.py`：列表灰背景、name/description 无列对齐

## 验收前提

- 输入框无 `>` 前缀
- 状态栏无背景、字体淡灰、模型信息与复制提示右对齐
- 目录 `~` 缩写、信息行顺序正确、末尾 `(auto)`
- 新建会话显示 logo + 操作提示 + skill + [Context] 栏
- 补全/选择列表无背景，name 列对齐、description 左对齐
- 用户消息 n+2 行全灰
- Markdown 正常换行、有序列表/表格解析正确
- 拖选复制真实写入剪贴板
