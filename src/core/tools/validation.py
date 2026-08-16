"""校验模型返回的工具参数。"""

from collections.abc import Mapping

from ..model import ToolCall
from .types import ToolDefinition


class ToolArgumentError(ValueError):
    """工具参数不符合定义时抛出的异常。"""


def validate_tool_arguments(
    definition: ToolDefinition,
    tool_call: ToolCall,
) -> None:
    """根据工具定义的最小 JSON Schema 校验调用参数。"""

    schema = definition.parameters
    arguments = tool_call.arguments
    if not isinstance(arguments, dict):
        raise ToolArgumentError("工具参数必须是 JSON 对象")

    required = schema.get("required", [])
    if not isinstance(required, list):
        raise ToolArgumentError("工具定义的 required 必须是数组")
    for name in required:
        if not isinstance(name, str) or name not in arguments:
            raise ToolArgumentError(f"缺少工具参数：{name}")

    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ToolArgumentError("工具定义的 properties 必须是对象")
    for name, value in arguments.items():
        property_schema = properties.get(name)
        if property_schema is None:
            continue
        if not isinstance(property_schema, Mapping):
            raise ToolArgumentError(f"参数定义无效：{name}")
        _validate_value(name, value, property_schema.get("type"))


def _validate_value(name: str, value: object, value_type: object) -> None:
    """校验单个参数的基础 JSON 类型。"""

    if value_type == "string" and not isinstance(value, str):
        raise ToolArgumentError(f"参数 {name} 必须是字符串")
    if value_type == "object" and not isinstance(value, dict):
        raise ToolArgumentError(f"参数 {name} 必须是对象")
    if value_type == "array" and not isinstance(value, list):
        raise ToolArgumentError(f"参数 {name} 必须是数组")
    if value_type == "boolean" and not isinstance(value, bool):
        raise ToolArgumentError(f"参数 {name} 必须是布尔值")
    if value_type == "integer" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        raise ToolArgumentError(f"参数 {name} 必须是整数")
    if value_type == "number" and (
        not isinstance(value, int | float) or isinstance(value, bool)
    ):
        raise ToolArgumentError(f"参数 {name} 必须是数字")
