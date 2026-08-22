# epsilon

一个简洁、可扩展的 Coding Agent（Python + prompt_toolkit）。

## 快速开始

```bash
uv run epsilon            # 首次运行进入配置引导
```

## 使用

- 在输入框输入问题，Enter 发送，Ctrl+J 换行
- 输入 `/` 查看全部命令
- Ctrl+D 退出

### Slash Commands

| 命令 | 说明 |
|---|---|
| `/model` | 查看/切换模型或新建配置 |
| `/thinking` | 选择推理强度档位（off/low/medium/high/xhigh） |
| `/skills` | 查看可用与已激活的 skill |
| `/start-skill` `/stop-skill` | 激活/停用 skill |
| `/mcp` | 查看注册的 MCP 工具 |
| `/background-image` | 管理终端背景图（查看/添加/透明度） |
| `/compact` | 手动压缩上下文 |
| `/status` | 显示会话配置与上下文用量 |
| `/copy` | 复制最后一条助手回复 |
| `/export` | 导出会话为 Markdown 文件 |
| `/diff` | 显示当前 git diff |
| `/clear` | 清空对话区展示 |
| `/quit` | 退出 |

### 终端支持说明

epsilon 的部分功能依赖终端能力，不同终端支持情况如下：

| 功能 | 支持终端 | 说明 |
|---|---|---|
| 背景图 `/background-image` | iTerm2（OSC 1337） | 其他终端下命令可用但会提示 `(unsupported in this terminal)` |
| Ctrl+滚轮缩放 | 终端原生缩放（Windows Terminal 等） | 应用不拦截时由终端直接缩放；iTerm2 等由 epsilon 发送字体序列 |
| 光标闪烁 | 依赖终端设置 | Windows Terminal 需在设置中开启「光标闪烁」 |
| 输入框 Markdown | 全部 | `**加粗**`、`` `code` `` 等会渲染 |

## 配置

配置保存在 `~/.epsilon/settings.json`（用户级）与 `<项目>/.epsilon/settings.json`（项目级，按字段覆盖）。

背景图配置（名称、路径、透明度）保存在项目级 `settings.json` 的 `background` 键。

## 测试

```bash
uv run pytest
```
