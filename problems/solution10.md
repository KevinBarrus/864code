# 第十轮优化方案

## 总体判断

本轮是 TUI 的深度重构：输入区样式、选择器布局、复制选区、状态栏、Markdown、工具着色、推理强度、价格表。参考 Pi 源码实现。按依赖顺序推进，每个子问题完成跑测试、提交。

## 建议执行顺序

1. **10.1 补全列表消失 bug**（问题三，独立小修，先清理）
2. **10.2 输入区水平线框 + 面板统一移到底部区域**（问题一/二/四，布局基础）
3. **10.3 状态栏两行式重构**（问题七，信息展示基础）
4. **10.4 推理强度 /thinking 命令**（问题九）
5. **10.5 价格表与用量统计**（问题十）
6. **10.6 整屏选区与复制**（问题五/六）
7. **10.7 对话区 Markdown 渲染**（问题八前半，先做基础）
8. **10.8 工具调用三色**（问题八后半）
9. 后续步骤：Markdown 完整版

## 问题一：输入区水平线框

- `screen.py`：输入区（TextArea 上下留白）去掉 `bg:#303030` 背景
- 输入区上下各加一个高度 1 的水平线 Window（内容 `─` 重复，蓝色前景 `#5f87ff`），对齐 Pi 的 `DynamicBorder`
- `theme.py`：`conversation-user` 背景保留，增加消息上下 padding（通过 ConversationView 的条目 Window 高度或样式内边距）

## 问题二/四：补全列表与选择器移到底部区域

- 输入区只保留 TextArea + 上下水平线
- 所有嵌入面板（审批 `ApprovalPrompt`、`ChoicePicker`、`SkillPicker`、`InputPrompt`、补全 `CommandPicker`）统一替换 `bottom_container.children`（输入区下方独立区域），不再替换 `input_container.children`
- `request_approval` / `request_skill_picker` / `request_choice_picker` / `request_text_input` 的布局挂载点改到 bottom 区域

## 问题三：删除 `/` 后补全列表不消失

- 定位删除字符后 `on_completions_changed` 是否触发、`complete_state` 是否清空
- 修复：删除到不以 `/` 开头时确保补全状态清除并恢复状态栏（可能需要在 `_on_input_text_changed` 中显式取消补全）

## 问题七：状态栏两行式

- 状态栏改两行（`bottom_container` 无补全时显示两行状态栏）：
  - 行一：左侧 `Working directory`，右侧复制提示（默认空）
  - 行二：左侧信息行（token/缓存/成本/上下文/余额），右侧 `(provider) modelName · level`
- 信息行数据来源：会话用量统计（10.5）、上下文用量（ContextManager）、余额（balance provider）
- 复制提示：`flash` 机制（天蓝色，5 秒消失），显示在行一右侧

## 问题九：推理强度 /thinking 命令

- `commands/thinking.py`：`/thinking` 命令，ChoicePicker 选档（`off/low/medium/high/xhigh`），默认 `high`
- 会话级状态：`ClientHolder` 或新 `ThinkingLevel` 状态，重启恢复 `high`
- `openai_client.py`：请求构造时按档位传 `reasoning_effort` 参数（off 不传或传最小）
- 状态栏右侧显示 `(deepseek) modelName · level`

## 问题十：价格表与会话成本

- `config.py`：`Settings` 加可选 `price`（`input/output/cache_read/cache_write`，每百万 tokens 单价）
- `model.py`：`UsageEvent` 扩展 `prompt_tokens` / `completion_tokens` / `cached_tokens`（服务端未返回时为 None）
- `openai_client.py`：从流式 usage 解析明细
- 新模块 `cost.py`：`UsageTotals`（会话累计 input/output/cache）+ `calculate_cost` 纯函数
- `ui.py`：每轮累加用量，信息行渲染 `↑↓R W CH $ % Balance`
- 缺失字段自动省略（无价格不显示 `$`，无缓存不显示 R/W/CH）

## 问题五/六：整屏选区与复制

- `screen.py`：捕获鼠标事件（按下/拖动/松开），记录选区 anchor/focus（行列）
- 选区渲染反色高亮（`\x1b[7m`），参考 Pi `applySelectionHighlight`
- 松开鼠标：计算选区文本 → OSC52（`\x1b]52;c;base64\x07`）写入剪贴板 → 显示复制提示（`Copied N chars to clipboard`，天蓝色，5 秒）
- 输入区 Ctrl+C 复制与整屏选区统一（选区优先）
- 对话区/输入区都支持拖选

## 问题八：Markdown 渲染 + 工具三色

- 基础版：标题、粗体/斜体、列表、代码块、引用、分隔线（对话条目渲染为 formatted text）
- 工具调用：`tool-activity` 条目改三色背景（pending `#282832` / success `#283228` / error `#3c2828`），对齐 Pi `tool-execution.ts`
- 后续步骤：Markdown 完整版（行内代码、链接、表格）

## 测试计划

- 布局：输入区水平线、面板挂载点、状态栏两行
- 补全：删除 `/` 后列表消失
- 推理强度：命令切换、默认值、请求参数
- 价格：配置解析、成本计算、缺字段省略
- 选区：拖选高亮、松开复制（mock OSC52）
- Markdown：基础语法渲染、工具三色
- 状态栏：信息行格式、复制提示显示与消失

## 验收标准

- 输入区上下水平线框住、无灰色背景
- 补全列表/选择器在输入区下方独立区域
- 删除 `/` 后补全列表消失
- 鼠标拖选反色高亮，松开自动复制 + 天蓝色提示 5 秒
- 状态栏两行式齐全
- `/thinking` 生效并显示在状态栏
- 会话成本按配置价格显示
- 对话区 Markdown 基础渲染、工具三色
- `uv run pytest` 全部通过

## 明确不做

- 推理强度写进 settings.json（会话级即可）
- Markdown 完整版一次性做完（分步）
- 成本价格内置（只用配置）
