# 第七轮优化方案

## 总体判断

实现「用户级 + 项目级」双级配置与 skill 体系，按子问题逐个推进，避免一次重构过大。每个子问题完成后跑测试、提交。

## 实施顺序（子问题）

### 7.1 配置源迁移（.env → settings.json）

- `config.py`：`load_settings()` 改为读用户级 `~/.epsilon/settings.json` + 项目级 `.epsilon/settings.json`，项目级字段级覆盖用户级
- settings.json 不存厂商名，只存 `base_url` / `api_key` / `model_name` 及可选预算字段
- 移除 python-dotenv 依赖（pyproject.toml）
- 更新 `main.py`、`evaluation/*.py` 的 `load_settings(env_path)` 调用点
- 删除项目根 `.env`

### 7.2 首次启动引导

- 检测 `~/.epsilon/settings.json` 缺失 → 进入引导：厂商选择器 → 输入 API key → 拉取模型列表 → 选默认模型 → 原子写入
- prompt-toolkit 独立小 app（复用 SessionPicker 模式），英文操作提示（Space 选择/取消、Enter 确认、Esc 退出）
- `--config` 参数跳过引导；Esc 取消安全退出；先写临时文件再原子重命名，保证不写半截文件

### 7.3 skill 目录迁移与多根扫描

- 项目 skill 从 `skills/` 迁移到 `.epsilon/skills/`
- `SkillManager` 支持多根扫描：项目 `.epsilon/skills/` + 全局 `~/.agents/skills/`，每根下 `<name>/SKILL.md`
- 扫描与解析逻辑复用

### 7.4 skill 来源标注与重名处理

- 选择器显示格式：`[] name [projects]` / `[] name [global]`，作用域后缀放最后，前导中括号标记勾选状态
- 重名时两个都显示；激活集合按 `(name, source)` 区分
- 注入内容的系统消息标注来源

### 7.5 /model 命令

- 展示当前配置、当前端点 `/models` 可用模型列表，以及「new config」选项
- new config：选厂商（预设 + 手动配置）→ 输入 API key → 拉取模型 → 保存到项目级 `.epsilon/settings.json`
- 热切换：`agent_loop.swap_client()` 更新主请求客户端；`ui.py` 的 `build_context` 闭包改用可变容器取当前客户端；重建 `ContextManager` budget；只在命令空闲间隙切换，不中断进行中的流式输出；不动已持久化的会话状态
- `/models` 拉取失败降级：只显示当前 `model_name` + 手动输入
- 项目级配置 v1 只做 model（含强度）；MCP 记为项目级但 v1 不改 UI

## 厂商预设列表

| 厂商 | base_url |
|---|---|
| DeepSeek | https://api.deepseek.com/ |
| OpenAI | https://api.openai.com/v1 |
| Moonshot | https://api.moonshot.cn/v1 |
| 阿里云百炼 | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| 智谱 | https://open.bigmodel.cn/api/paas/v4 |
| 硅基流动 | https://api.siliconflow.cn/v1 |
| 手动配置 | 用户输入 base_url |

## 测试计划

- 配置：用户级读取、项目级字段级覆盖、缺失时触发引导、JSON 解析错误容错
- 引导：厂商选择、API key 输入、模型选择、原子写入、Esc 取消不写半截、`--config` 跳过
- skill：多根扫描、来源标注、重名区分、激活按 `(name, source)`、注入带来源
- /model：模型列表拉取、new config 流程、热切换（主请求与压缩都走新模型）、`/models` 失败降级

## 验收标准

- 不依赖 `.env`，配置从用户级读、项目级可覆盖
- 首次启动引导可用，取消不写半截文件
- `/model` 切换模型并热生效（主请求和压缩都走新模型）
- skill 双级合并、来源标注、重名区分
- `uv run pytest` 全部通过

## 明确不做

- 项目级 MCP 配置 UI（v1 只做 model）
- 全局 skill 的跨文件引用（如 lark-* 读 `../lark-shared/`，read_file 限工作区，v1 记为已知边界）
- 配置热更新的并发保护（只在命令空闲间隙切换）
