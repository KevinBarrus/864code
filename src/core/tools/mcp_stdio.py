"""通过标准输入输出连接 MCP Server。"""

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..model import ToolCall, ToolResult
from .mcp import McpToolProvider
from .types import ToolDefinition


class McpProtocolError(RuntimeError):
    """MCP Server 返回无效响应时抛出的异常。"""


class StdioMcpProvider(McpToolProvider):
    """管理一个通过 stdin/stdout 通信的 MCP Server 子进程。"""

    def __init__(
        self,
        command: Sequence[str],
        provider_id: str,
        cwd: Path | None = None,
    ) -> None:
        """保存 MCP Server 启动命令和提供者身份。"""

        if not command:
            raise ValueError("MCP Server 启动命令不能为空")
        if not provider_id:
            raise ValueError("MCP provider_id 不能为空")
        self._command = tuple(command)
        self._provider_id = provider_id
        self._cwd = cwd
        self._process: asyncio.subprocess.Process | None = None
        self._next_request_id = 1
        self._request_lock = asyncio.Lock()

    async def list_tools(self) -> Sequence[ToolDefinition]:
        """初始化 MCP Server 并返回远程工具定义。"""

        result = await self._request("tools/list", {})
        raw_tools = result.get("tools", [])
        if not isinstance(raw_tools, list):
            raise McpProtocolError("tools/list 返回的 tools 不是数组")

        definitions: list[ToolDefinition] = []
        for raw_tool in raw_tools:
            if not isinstance(raw_tool, Mapping):
                raise McpProtocolError("MCP 工具定义不是对象")
            name = raw_tool.get("name")
            description = raw_tool.get("description", "")
            schema = raw_tool.get("inputSchema", {"type": "object"})
            if not isinstance(name, str) or not name:
                raise McpProtocolError("MCP 工具缺少有效名称")
            if not isinstance(description, str) or not isinstance(schema, dict):
                raise McpProtocolError(f"MCP 工具定义无效：{name}")
            annotations = raw_tool.get("annotations", {})
            if not isinstance(annotations, Mapping):
                raise McpProtocolError(f"MCP 工具 annotations 无效：{name}")
            read_only = annotations.get("readOnlyHint") is True
            definitions.append(
                ToolDefinition(
                    name=name,
                    description=description,
                    parameters=schema,
                    source="mcp",
                    permission="read" if read_only else "write",
                    idempotent=annotations.get("idempotentHint") is True,
                    provider_id=self._provider_id,
                )
            )
        return definitions

    async def call_tool(self, tool_call: ToolCall) -> ToolResult:
        """调用 MCP 工具并转换为统一工具结果。"""

        try:
            result = await self._request(
                "tools/call",
                {"name": tool_call.name, "arguments": tool_call.arguments},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return ToolResult(tool_call.call_id, f"MCP 调用失败：{exc}", True)

        content = result.get("content", [])
        if not isinstance(content, list):
            return ToolResult(tool_call.call_id, "MCP 工具结果格式无效", True)
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "text"
        ]
        text = "\n".join(part for part in text_parts if isinstance(part, str))
        return ToolResult(
            tool_call.call_id,
            text,
            bool(result.get("isError", False)),
        )

    async def close(self) -> None:
        """关闭 MCP Server 子进程。"""

        if self._process is None:
            return
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None

    async def _request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        """发送一个串行 JSON-RPC 请求并读取对应响应。"""

        async with self._request_lock:
            await self._ensure_started()
            assert self._process is not None
            assert self._process.stdin is not None
            assert self._process.stdout is not None

            request_id = self._next_request_id
            self._next_request_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            self._process.stdin.write((json.dumps(payload) + "\n").encode())
            await self._process.stdin.drain()

            while True:
                line = await self._process.stdout.readline()
                if not line:
                    raise McpProtocolError("MCP Server 已退出")
                response = json.loads(line)
                if response.get("id") != request_id:
                    continue
                if "error" in response:
                    raise McpProtocolError(str(response["error"]))
                result = response.get("result")
                if not isinstance(result, dict):
                    raise McpProtocolError("MCP 响应缺少 result 对象")
                return result

    async def _ensure_started(self) -> None:
        """按需启动进程并完成 MCP 初始化握手。"""

        if self._process is not None:
            if self._process.returncode is not None:
                raise McpProtocolError("MCP Server 已退出")
            return

        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            cwd=self._cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self._request_without_lock(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "864code", "version": "0.1.0"},
            },
        )
        await self._send_notification("notifications/initialized", {})

    async def _request_without_lock(
        self,
        method: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """在已持有请求锁时完成一次请求。"""

        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        request_id = self._next_request_id
        self._next_request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._process.stdin.write((json.dumps(payload) + "\n").encode())
        await self._process.stdin.drain()
        while True:
            line = await self._process.stdout.readline()
            if not line:
                raise McpProtocolError("MCP Server 已退出")
            response = json.loads(line)
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise McpProtocolError(str(response["error"]))
            result = response.get("result")
            if not isinstance(result, dict):
                raise McpProtocolError("MCP 响应缺少 result 对象")
            return result

    async def _send_notification(self, method: str, params: dict[str, object]) -> None:
        """发送不需要响应的 JSON-RPC 通知。"""

        assert self._process is not None
        assert self._process.stdin is not None
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self._process.stdin.write((json.dumps(payload) + "\n").encode())
        await self._process.stdin.drain()
