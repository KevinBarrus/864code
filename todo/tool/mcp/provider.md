# MCP Provider 命令行配置

## 目标

让用户可以通过配置文件或命令行配置 MCP Server，启动 864code 时自动发现并注册 MCP 工具

## 待完成事项

- 设计最小 MCP Server 配置格式
- 支持配置启动命令、参数、工作目录和 `provider_id`
- 启动时创建 `StdioMcpProvider`
- 调用 `ToolManager.register_mcp_provider`
- 处理 MCP Server 启动失败、退出和响应异常
- 在 TUI 中区分本地工具和 MCP 工具的摘要
- 增加配置加载和完整启动流程测试

## 暂不处理

- MCP Server 网络传输
- 多进程连接池
- 动态热加载配置
- MCP 工具输出截断
