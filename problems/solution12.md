# 第十二轮优化方案

## 总体判断

本轮继续完善 Markdown 与代码着色，增强输入框、光标、选项交互，实现 Logo 方块字与背景图功能，扩展 slash command，升级 resume 界面。按依赖顺序推进，每个子问题完成跑测试、提交。

## 建议执行顺序

1. **12.1 Markdown 与代码着色**（问题二/三）
2. **12.2 输入框增强**（问题四/五）
3. **12.3 光标闪烁 + 选项鼠标点击**（问题九/十）
4. **12.4 扩展 slash command**（问题十一）
5. **12.5 Logo 方块字 + 引导 + 对话区化**（问题一/七）
6. **12.6 屏幕缩放**（问题六）
7. **12.7 背景图功能**（问题八）
8. **12.8 resume 界面 Codex 风格 + /delete**（问题十二）
9. **12.9 输入框 Markdown**（问题十三）

## 问题二/三：Markdown 与代码着色

- `render_markdown` 引用分支调用 `render_inline`，修复引用行内粗体/代码/链接未解析
- 未闭合标记：`**`/`` ` `` 出现时忽略符号本身，只保留文字（放弃加粗/代码效果）
- theme.py：`md-code`/`md-code-block` 改青色字体（去掉灰背景），新增 `tool-diff-add`（绿）/`tool-diff-del`（红）
- 工具写/编辑结果解析 diff 内容，新增行绿色、删除行红色

## 问题四/五：输入框增强

- `_get_input_line_prefix` 删除前导空格（水平留白改为 0，或删除前缀函数）
- 输入框超行时上边界左侧显示 `─── ↑ n more`（检测 TextArea 滚动/折叠行数）
- 确认粘贴大文本在 TextArea 内自动换行（wrap_lines=True 已设，验证修复）

## 问题九/十：光标与选项交互

- 光标：验证并修复 BLINKING_BEAM 闪烁（可能需在 full_screen 下强制输出 DECSCUSR 或确认终端支持）
- ChoicePicker/SkillPicker/CommandPicker 行加鼠标点击处理器：点击行选中，再次点击确认

## 问题十一：扩展 slash command

- 新增命令（对齐 Codex 核心）：/compact /clear /new /rename /copy /diff /status /usage /skills /mcp /quit /resume /delete
- 延续 registry 模式：每个命令一个文件 + 注册，分层解耦

## 问题一/七：Logo 方块字 + 对话区化

- logo 改为对话区第一条内容（新建会话时作为首条消息加入对话，随对话滚动）
- `ε - EPSILON` 方块字 ASCII art（DefaultLogoProvider 替换为方块字渲染）
- 下方引导：/ 命令（/model /compact /skills /mcp）、↑/↓+鼠标选择、背景图、缩放、输入框 markdown 说明

## 问题六：屏幕缩放

- 检测 Ctrl+滚轮事件，发送字体缩放转义序列（iTerm2 OSC 50 等支持终端）
- 不支持时自然放行（Windows Terminal 原生缩放）

## 问题八：背景图

- 新增 `/background-image` 命令（commands/background_image.py）
- 三级菜单：current options（粉红 (current) 切换）/ add options（名字+路径）/ transparency（两位小数）
- 配置持久化到 settings.json（backgrounds 列表 + current + transparency）
- 应用时检测终端能力：支持发 OSC 序列，不支持显示 `(unsupported in this terminal)`
- 图片格式校验（png/jpg/jpeg/gif/webp）

## 问题十二：resume 界面 + /delete

- resume picker 改 Codex 风格：多行记录（标题/预览 + 相对时间 + 工作目录），选中高亮，zebra 交替，/ 搜索过滤
- 新增 /delete 命令：删除当前会话（先 trash 后 unlink），删除后退出

## 问题十三：输入框 Markdown

- 用户消息渲染 Markdown（复用 render_markdown），发送后对话区加粗生效
- 前置信息说明输入框支持 Markdown

## 测试计划

- markdown：引用 inline、未闭合标记、代码青色、diff 红绿
- 输入框：前缀、↑ n more、粘贴 wrap
- 光标闪烁、选项鼠标点击
- 新命令注册与分发
- logo 方块字 + 对话区化
- 缩放事件、背景图命令与配置持久化
- resume 界面 + /delete

## 验收标准

- Logo 随对话滚动，方块字 + 引导
- 引用行内粗体解析、未闭合标记无符号残留
- 模型代码青色、工具 diff 红绿
- 输入框无前导空格、超行 ↑ n more、粘贴 wrap
- 光标闪烁、选项鼠标点击
- Codex 核心命令齐全
- Ctrl+滚轮缩放（支持终端）或原生缩放
- 背景图命令可用，不支持终端有降级提示
- resume Codex 风格 + /delete
- 输入框 markdown 渲染
- `uv run pytest` 全部通过

## 明确不做

- 文件资源管理器选图（先输入路径）
- resume 里删除会话（用 /delete）
- 背景图动画/渐变等花哨效果
