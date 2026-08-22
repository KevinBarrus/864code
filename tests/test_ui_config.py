from core.ui_config import InputLayoutConfig


def test_input_layout_config_has_readable_defaults() -> None:
    """测试输入区域默认使用明确且集中的尺寸配置。"""

    config = InputLayoutConfig()

    assert config.max_lines == 8
