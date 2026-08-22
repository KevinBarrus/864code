"""通过 OSC52 转义序列读写系统剪贴板，不依赖外部程序。"""

import base64
import sys

from prompt_toolkit.application import get_app
from prompt_toolkit.clipboard import Clipboard, ClipboardData


def _write_osc52(payload: str) -> None:
    """把 base64 负载写入终端，优先使用活动应用的输出通道。"""

    sequence = f"\x1b]52;c;{payload}\x07"
    try:
        app = get_app()
    except Exception:
        sys.stdout.write(sequence)
        sys.stdout.flush()
    else:
        app.output.write_raw(sequence)
        app.output.flush()


class Osc52Clipboard(Clipboard):
    """写入系统剪贴板并保留内存副本，供粘贴使用。"""

    def __init__(self) -> None:
        """初始化空的内存副本。"""

        self._memory = ClipboardData()

    def set_data(self, data: ClipboardData) -> None:
        """编码文本写入系统剪贴板，同时保留内存副本。"""

        self._memory = data
        payload = base64.b64encode(data.text.encode("utf-8")).decode("ascii")
        _write_osc52(payload)

    def set_text(self, text: str) -> None:
        """便捷入口：写入纯文本。"""

        self.set_data(ClipboardData(text))

    def get_data(self) -> ClipboardData:
        """返回内存中的最近一次复制内容。"""

        return self._memory

    def rotate(self) -> None:
        """无历史剪贴板，旋转不做任何事。"""


def copy_text_to_clipboard(text: str) -> None:
    """把一段文本直接写入系统剪贴板，供对话区拖选复制使用。"""

    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    _write_osc52(payload)
