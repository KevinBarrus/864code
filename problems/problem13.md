# 问题 13：Logo 修复与艺术化、语法高亮、居中、补全滚动、思考展示、working/重试、折叠、输入框重构、自动复制、缩放

## 发现来源

用户验收第十二轮后反馈的 11 个问题，参考 Pi（syntax-highlight.ts 用 highlight.js、status-indicator.ts 的 Working/Retry、loader.ts 的 spinner 帧、bash-execution.ts 的折叠文案、assistant-message.ts 的 thinking 块）对齐方案。

## 问题一：Logo 展示不完全（已定位根因）

ConversationView 新建会话时 follow_output=True，write_to_screen 滚动到底部（vertical_scroll = 内容高度 - 视口高度）。logo+引导 11 行超过对话区视口高度时顶部被滚出屏幕。

修复：仅当存在用户/助手消息时才跟随底部；仅有 logo 时保持顶部显示。

## 问题二：代码语法高亮（多语言）

- 对齐 Pi（highlight.js）用 Pygments（Python 语法高亮库）
- 保留 ```语言名，代码区按 token 着色：关键字/字符串/注释/数字/函数名不同色
- **多语言分层解耦**：新增一种语言只需在语言注册表加一行/几行（Pygments 已内置 300+ 语言，需要定制时按语言配置 token 颜色映射）
- 颜色集中在 theme.py

## 问题三：前置信息居中

logo 与引导整体居中显示（正式感），按终端宽度计算缩进。

## 问题四：补全列表滚动 bug（已定位根因）

- on_completions_changed 每次重建 CommandPicker（cursor 归 0）→ prompt_toolkit complete_while_typing debounce（约 1 秒）重算 → 回第一项
- ↑/↓ 与 prompt_toolkit 内置补全导航冲突，vertical_scroll 被重置

修复：不重建 picker（增量更新）、↑/↓ eager 接管、滚动状态保留。

## 问题五：思考过程展示

- 事件层 TextDelta 扩展支持 reasoning（DeepSeek reasoning_content）
- /thinking-toggle 命令：切换思考块显示/隐藏，隐藏时显示斜体 "Thinking..." 标签
- 命令分层解耦（名称集中定义，改名只动一处）

## 问题六：working/重试展示

- epsilon 有重试机制（agent_loop._retry_stream，network→retry max_attempts=2，指数退避）但无 UI 展示
- 参考 Pi：WorkingStatusIndicator（spinner 帧 ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ 80ms + 消息）、RetryStatusIndicator（Retrying (n/m) in Xs... 倒计时）
- 模型思考中/工具执行中显示 working + 耗时；重试时显示 Retrying + 倒计时

## 问题七：大工具输出折叠

对齐 Pi：`... N more lines (ctrl+o to expand)`，工具输出超限折叠，ctrl+o 展开/折叠。

## 问题八：光标闪烁

代码层已正确（BLINKING_BEAM + 每次渲染重发 \x1b[5 q），依赖终端设置（Windows Terminal 默认关闭光标闪烁），需用户确认终端设置。

## 问题九：输入框重构（Pi 方案）

- 输入框作为对话区最下方，随对话滚动自然下移出屏幕
- 输入框内不再支持鼠标滚动
- 排查多行超上限底部多空行 bug

## 问题十：输入框自动复制 + /auto-copy

- 输入框内选中松开自动复制（对话区已做，输入框补上）
- /auto-copy 命令切换开关，状态不显示在状态栏

## 问题十一：缩放（已定位根因）

prompt_toolkit 启用 SGR 1006 鼠标模式（\x1b[?1006h）→ Windows Terminal 把 Ctrl+滚轮发给应用（不保留为终端缩放）→ epsilon 发 OSC 50 不被支持 → 缩放失效。

修复：自定义输出层不启用 1006（只 1000+1003）→ Windows Terminal 恢复原生 Ctrl+滚轮缩放，拖选/滚轮仍工作。

## 现有代码缺口

- conversation_view：follow 滚动逻辑（logo 顶部被滚出）
- markdown：代码块无语法高亮、无语言名
- screen：logo/引导左对齐、CommandPicker 重建、输入框内置滚轮、无自动复制
- agent_loop：retry 无事件暴露
- 无 thinking 事件、无 working 指示器、无工具折叠、无 /thinking-toggle /auto-copy

## 验收前提

- Logo 完整显示并随对话上移
- 多语言代码语法高亮（保留语言名）
- logo/引导居中
- 补全列表滚动正常、不自动回第一项
- /thinking-toggle 切换思考展示
- 模型思考/工具执行/重试有 working 展示
- 工具大输出折叠 + ctrl+o 展开
- 输入框 Pi 式布局（随对话滚动）、无鼠标滚动
- 输入框选中自动复制 + /auto-copy
- Ctrl+滚轮缩放生效
