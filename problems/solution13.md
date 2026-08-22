# 第十三轮优化方案

## 总体判断

本轮包含两个根因明确的 bug 修复（logo 顶部被滚出、SGR 1006 拦截缩放）、两个交互重构（补全列表、输入框 Pi 式布局）、一个多语言语法高亮（Pygments）、思考/working/重试展示、工具折叠、自动复制。按依赖顺序推进。

## 建议执行顺序

1. **13.1 补全列表滚动修复**（问题四）
2. **13.2 Logo 展示修复 + 居中**（问题一/三）
3. **13.3 语法高亮（Pygments 多语言）**（问题二）
4. **13.4 思考过程展示 /thinking-toggle**（问题五）
5. **13.5 working/重试展示**（问题六）
6. **13.6 大工具输出折叠**（问题七）
7. **13.7 输入框 Pi 式重构**（问题九）
8. **13.8 输入框自动复制 + /auto-copy**（问题十）
9. **13.9 缩放修复（禁用 SGR 1006）**（问题十一）

## 问题四：补全列表滚动修复

- CommandPicker 改为增量更新（不重建）：_on_completions_changed 只在列表变化时替换 completions，保留 cursor 与滚动位置
- ↑/↓ eager 接管（key_bindings 加 eager=True），避免 prompt_toolkit 内置补全导航冲突
- 核对 _follow_cursor 滚动逻辑与 Window 高度

## 问题一/三：Logo 展示 + 居中

- ConversationView：仅在存在对话消息时 follow 底部；新建（仅 logo）时保持顶部
- logo 与引导按终端宽度居中：_render_logo 返回前按 width 计算每行缩进（需知道宽度，用 FormattedTextControl callable 接收宽度或存 last width）

## 问题二：语法高亮

- 新增依赖 pygments
- markdown.py 代码块：识别 ```语言名，用 Pygments 分词，token 映射到样式类（md-tok-keyword/string/comment/number/function 等）
- 语言注册表（LANGUAGE_REGISTRY）：默认 Pygments 自动识别；特殊语言（如 epsilon 专属）可覆盖
- 新增语言只需注册表加一行；颜色集中在 theme.py

## 问题五：思考过程展示

- 事件层：TextDelta 增加 reasoning 字段（DeepSeek reasoning_content）
- agent_loop/openai_client 采集 reasoning
- UI：思考块渲染（可折叠）+ /thinking-toggle 切换显示/隐藏
- 命令名集中定义，改名只动一处

## 问题六：working/重试展示

- 新增 WorkingIndicator（spinner 帧 ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ 80ms）
- agent_loop 暴露事件：模型请求开始/工具执行开始（含耗时）
- UI：状态栏/底部显示 working for xx s（思考中）、工具执行中
- 重试：_retry_stream 发 RetryEvent → UI 显示 Retrying (n/m) in Xs...（倒计时）

## 问题七：工具输出折叠

- 工具结果 > N 行（如 8 行）折叠，显示 ... N more lines (ctrl+o to expand)
- ctrl+o 展开/折叠（对齐 Pi app.tools.expand）

## 问题九：输入框 Pi 式重构

- 布局：对话区与输入框一体（输入框在对话内容末尾），随滚动下移出屏幕
- 输入框不再响应鼠标滚轮（禁用滚轮绑定）
- 排查多行超上限底部多空行问题

## 问题十：输入框自动复制

- TextArea 选区变化检测：选中松开即复制（Osc52Clipboard）
- /auto-copy 命令切换开关（on/off），不显示状态栏

## 问题十一：缩放修复

- 自定义 output 子类：enable_mouse_support 只写 1000+1003（不写 1006）
- Windows Terminal 恢复原生 Ctrl+滚轮缩放；拖选/普通滚轮仍工作

## 测试计划

- 补全：滚动、不重建保留 cursor、eager 键
- logo：新建时顶部显示、有消息后跟随底部、居中
- 语法高亮：多语言 token 着色、语言名保留
- thinking：事件采集、/thinking-toggle 切换
- working/重试：spinner 展示、RetryEvent
- 折叠：N more lines + ctrl+o
- 输入框：Pi 式布局、无鼠标滚动、自动复制、/auto-copy
- 缩放：1000/1003 启用、1006 禁用

## 验收标准

- Logo 完整显示、居中、随对话上移
- 代码多语言高亮 + 语言名
- 补全列表滚动正常
- /thinking-toggle 生效
- working/Retrying 展示
- 工具折叠 + ctrl+o
- 输入框 Pi 式布局、自动复制、/auto-copy
- Ctrl+滚轮缩放生效
- uv run pytest 全部通过

## 明确不做

- 光标闪烁（终端设置，代码已正确）
- 背景图/缩放之外的终端特性
- logo 笔迹图片（用户自行提供，LogoProvider 接口保留）
