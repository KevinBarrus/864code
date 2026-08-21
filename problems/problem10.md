# 问题 10：输入区样式、复制选区、状态栏重构、Markdown 与工具着色、推理强度、价格表

## 发现来源

用户实际使用 TUI 后反馈的 8 个问题，并参考 Pi 源码（`~/projects/pi/packages/tui/` 与 `packages/coding-agent/src/modes/interactive/`）对齐输入区、状态栏、选区复制、推理强度的实现，同时新增推理强度控制与价格表两项能力。

## 问题一：输入区样式错误

状态栏嵌入输入区里（背景与输入区一样灰色），整体是 Codex 式灰色背景块。改用 Pi 风格：输入区用**上下两条水平线**框住（蓝色边框），历史用户消息保留灰色背景但**上下留白加大**。

## 问题二：补全列表嵌入输入区

因问题一，输入 `/` 后补全列表也显示在输入区背景内。补全列表应显示在输入区**下方独立区域**，自带背景。

## 问题三：删除 `/` 后补全列表不消失

输入 `/` 显示列表后，删除 `/` 列表仍显示（bug）。删除字符后应恢复状态栏。

## 问题四：选择器占满输入区

select model 及后续所有选择器（ChoicePicker/SkillPicker/InputPrompt/审批）嵌入输入区并占满。选择器应统一显示在输入区**下方独立区域**，输入区只保留文本输入。

## 问题五：输入区 Ctrl+C 不能复制

输入区文本可选中但 Ctrl+C 不复制。并入整屏选区方案统一处理。

## 问题六：对话区文本不能选中复制

对话区文本无法选中。采用「鼠标拖选（反色高亮）→ 松开自动复制」机制（参考 Pi fullscreen 模式 `tui-alt-screen.ts` 的选区逻辑），避免 Ctrl+C 误触退出。

## 问题七：状态栏改 Pi 模式

两行式状态栏（参考 Pi `footer.ts`）：
- 行一：左侧工作区；右侧复制提示（`Copied N chars to clipboard`，天蓝色，5 秒消失，平时空）
- 行二：左侧信息行（`↑{in} ↓{out} R{read} W{write} CH{hit}% ${cost} {percent}%/{window} Balance`）；右侧 `(provider) modelName · level`（厂商名从 base_url 推断）

## 问题八：Markdown 无法解析 + 工具着色单一

- 对话区 Markdown 格式无法解析，需渲染（完整版：标题/粗体/斜体/列表/代码块/行内代码/链接/引用/表格，分步推进先做基础）
- 工具调用背景色单一，改为三种（待执行/成功/错误，参考 Pi `tool-execution.ts`：`#282832` / `#283228` / `#3c2828`）

## 问题九：推理强度控制（新增能力）

新增 `/thinking` slash command（单独命令，不做 settings 菜单）：
- 选项 `off / low / medium / high / xhigh`（复用 ChoicePicker 样式）
- 默认 `high`（会话级，重启恢复 high），`off` 供手动关闭
- deepseek 实测支持 `reasoning_effort` 参数，请求直接传对应档位
- 状态栏右侧显示 `(deepseek) deepseek-v4-pro · high`

## 问题十：价格表与会话成本（新增能力）

- 价格从 settings.json 的 `model.price` 配置（每百万 tokens 单价，`input/output/cache_read/cache_write`），不写死厂商价格
- 分层解耦：用量采集（UsageEvent 扩展明细）→ 价格配置 → 成本纯函数 → 会话累计 → 展示
- 信息行显示 `$cost`，缺失字段自动省略

## 现有代码缺口

- `screen.py`：输入区灰色背景、嵌入面板机制、状态栏单行、无选区
- `model.py`：UsageEvent 只有 total，无明细
- `config.py`：无 price 字段
- 无 `/thinking` 命令、无成本计算模块、无 Markdown 渲染、无整屏选区

## 验收前提

- 输入区上下水平线框住，无灰色背景；用户消息背景留白加大
- 补全列表/选择器在输入区下方独立区域
- 删除 `/` 后补全列表消失、状态栏恢复
- 鼠标拖选反色高亮，松开自动复制并显示天蓝色提示（5 秒消失）
- 状态栏两行式：工作区/信息行/复制提示行/模型名·推理强度
- 对话区 Markdown 渲染、工具调用三色
- `/thinking` 切换推理强度并生效，状态栏同步
- 会话成本按配置价格计算并显示
