# 问题 12：Logo 对话区化、Markdown 完善、代码着色、输入框增强、缩放、背景图、命令扩展与 resume 界面

## 发现来源

用户实际验收第十一轮后反馈的 13 个问题，参考 Codex（slash_command.rs 命令清单、resume_picker.rs 会话选择界面、event_dispatch.rs 删除接口）、Pi（session-selector.ts 删除接口、editor.ts ↑ n more、user-message.ts Markdown）、Reasonix（欢迎页）对齐方案。

## 问题一：Logo 应作为对话区第一部分

Logo 不应固定显示在屏幕顶部，而应作为对话区的第一条内容，随对话增长自然上移出屏幕。

## 问题二：Markdown 解析残留

- 引用行内粗体（`> **文字**`）未解析，`**` 原样显示
- 未闭合的 `**`/反引号标记原样显示（星号残留），应忽略标记（不显示符号、放弃加粗）

## 问题三：代码着色

- 模型返回代码块取消灰色背景，改用**青色**字体区分
- 工具调用写/编辑代码做 diff 红绿标记
- 所有颜色值集中在 theme.py，其它文件只引用样式类名，不出现具体色值

## 问题四：输入框增强

- 输入超过最大行数时，输入框上边界左侧显示 `─── ↑ n more`
- 粘贴大文本在输入框内自动换行显示

## 问题五：输入框前导空格

输入框文字前多了一个空字符，首字应贴最左，删除前导留白。

## 问题六：屏幕缩放

支持 Ctrl+滚轮或触摸板缩放。触摸板 pinch 本质由终端处理（或转成 Ctrl+滚轮），epsilon 检测 Ctrl+滚轮发送字体缩放序列（支持终端才生效），WSL/Windows Terminal 原生缩放自然生效。

## 问题七：Logo 设计

展示 `ε - EPSILON` 方块字（命令行方块拼成），下方引导基本操作：`/` 命令（/model /compact /skills /mcp）、↑/↓+鼠标选择、切换背景图、屏幕缩放等。

## 问题八：背景图功能

`/background-image` 命令：current options（查看/切换配置，当前项粉红标 (current)）、add options（名字+图片路径）、transparency（透明度两位小数）。配置持久化到 settings.json；对不支持的终端显示降级提示，README 与前置信息说明终端支持情况。

## 问题九：光标不闪烁

光标应始终闪烁（Claude Code 风格）。

## 问题十：选项鼠标点击

选项既支持鼠标点击选中/确认，也支持上下箭头+Enter。

## 问题十一：扩展 slash command

与 Codex 核心 slash command 保持一致：/compact /clear /new /rename /copy /diff /status /usage /skills /mcp /quit /resume /delete 等。

## 问题十二：resume 界面与删除会话

- resume 界面做成 Codex 风格（多行会话记录 + 相对时间 + 工作目录 + 预览，选中高亮、zebra 交替行）
- 删除会话用单独命令（resume 里不做删除），删除接口先 trash 后 unlink

## 问题十三：输入框 Markdown

输入框支持 Markdown 语法（`**加粗**` 发送后在对话区渲染加粗），前置信息中说明此行为。

## 现有代码缺口

- `markdown.py`：引用行内未解析、未闭合标记残留、代码块灰背景
- `theme.py`：代码块用 bg，需改青色字体；需加 diff 红绿样式
- `screen.py`：logo 固定容器、输入框前导空格、光标闪烁、选项无鼠标
- `ui.py`：无 diff 红绿显示、输入框 markdown 未渲染
- 无 `/background-image`、扩展命令、resume 界面升级

## 验收前提

- Logo 随对话滚动上移
- 引用行内粗体解析、未闭合标记不显示符号
- 模型代码青色、工具 diff 红绿
- 输入框无前导空格、超行显示 ↑ n more、粘贴 wrap
- Ctrl+滚轮缩放（支持终端）或原生缩放
- 光标始终闪烁
- 选项支持鼠标点击
- Codex 核心命令齐全
- resume 界面 Codex 风格 + /delete 命令
- 输入框 markdown 渲染
