import json
import sys
from pathlib import Path

import pytest

from core.model import ToolCall
from core.tools import StdioMcpProvider


SERVER = r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "notifications/initialized":
        continue
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "test"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "remote_echo", "description": "回显", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": request["params"]["arguments"]["text"]}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
'''


@pytest.mark.asyncio
async def test_stdio_provider_lists_and_calls_tools(tmp_path: Path) -> None:
    """测试 stdio Provider 可以握手、发现和调用工具。"""

    provider = StdioMcpProvider(
        [sys.executable, "-u", "-c", SERVER],
        provider_id="test-server",
        cwd=tmp_path,
    )

    definitions = await provider.list_tools()
    result = await provider.call_tool(
        ToolCall("call-1", "remote_echo", {"text": "hello"})
    )
    await provider.close()

    assert definitions[0].name == "remote_echo"
    assert definitions[0].provider_id == "test-server"
    assert result.content == "hello"
    assert result.is_error is False
