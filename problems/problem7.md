# 问题 7：配置与 skill 的「用户级 + 项目级」体系缺失

## 发现来源

本问题整理自与用户关于「epsilon 如何像市面上的 Coding Agent 一样管理配置与 skill」的多轮设计讨论。讨论覆盖配置来源、skill 目录层级、模型切换、首次启动引导等，最终形成明确取舍。

## 总体判断

epsilon 目前的配置和 skill 都绑定在单个项目内：

- 配置只读项目根 `.env`（dotenv），用户每进入一个项目都要手动建 `.env` 填 API key，且容易和项目自身的 `.env` 混淆
- skill 只扫项目根 `skills/`，没有全局 skill；`~/.agents/skills/` 的共享全局 skill 读不到
- 没有模型切换命令（`/model`），想换模型只能改配置
- 没有首次启动引导，用户要手动写配置文件

本次补齐「用户级 + 项目级」双级体系，并按子问题拆分逐步解决。

## 设计决策（来自讨论的取舍）

1. **配置双级**：用户级 `~/.epsilon/settings.json` 是默认；项目级 `.epsilon/settings.json` 覆盖，优先级更高，可包含自己的 API key
2. **完全移除 .env**：不再读 dotenv，避免与项目自身 `.env` 混淆；移除 python-dotenv 依赖
3. **skill 双级**：项目 skill 放 `.epsilon/skills/`（gitignored，是开发者用的）；全局 skill 复用 `~/.agents/skills/`（共享目录）
4. **模型切换走 `/model`**：展示当前端点可用模型，支持「new config」换厂商/端点/API key，热切换
5. **首次启动引导**：settings.json 缺失时交互式引导（选厂商 → API key → 选模型 → 原子写入），`--config` 跳过
6. **skill 重名**：项目与全局重名时两个都显示，来源后缀 `[projects]` / `[global]` 区分，激活集合按 `(name, source)` 区分

## 现有代码缺口

- `config.py` 只支持 dotenv 读取，无 JSON、用户级、项目级覆盖
- `skills/manager.py` 只扫项目根 `skills/`，无多根、无来源标注
- 无 `/model` 命令、无模型列表拉取、无热切换
- 无首次启动引导
- `evaluation/` 大量 `load_settings(env_path)` 调用点依赖 dotenv

## 验收前提

- 配置从用户级读，项目级可覆盖；不再依赖 `.env`
- skill 从 `.epsilon/skills/` + `~/.agents/skills/` 合并，来源标注、重名区分
- `/model` 能切换模型并热生效
- 首次启动引导可用，`--config` 可跳过，取消不写半截文件
