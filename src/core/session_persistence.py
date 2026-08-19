"""提供按顺序写入 Session 的后台持久化队列。"""

from __future__ import annotations

from collections.abc import Callable
from queue import Queue
from threading import Lock, Thread

from .model import Message


PersistMessage = Callable[[Message], None]
PersistPendingMessage = Callable[[Message], None]
_STOP = object()


class SessionPersistenceQueue:
    """异步追加消息，并在持久化失败后保留未写入消息。"""

    def __init__(
        self,
        persist_message: PersistMessage,
        max_retries: int = 2,
        persist_pending: PersistPendingMessage | None = None,
    ) -> None:
        """创建后台写入线程和有界重试策略。"""

        if max_retries < 0:
            raise ValueError("持久化重试次数不能小于 0")
        self._persist_message = persist_message
        self._persist_pending = persist_pending or (lambda message: None)
        self._max_retries = max_retries
        self._queue: Queue[Message | object] = Queue()
        self._pending: list[Message] = []
        self._lock = Lock()
        self._degraded = False
        self._closed = False
        self._worker = Thread(target=self._run, name="session-persistence", daemon=True)
        self._worker.start()

    def enqueue(self, message: Message) -> None:
        """按消息产生顺序加入持久化队列。"""

        with self._lock:
            if self._closed:
                raise RuntimeError("Session 持久化队列已关闭")
        self._queue.put(message)

    def flush(self) -> bool:
        """等待当前队列处理完成，并返回是否全部写入成功。"""

        self._queue.join()
        with self._lock:
            return not self._degraded and not self._pending

    def close(self) -> bool:
        """刷新队列并停止后台写入线程。"""

        with self._lock:
            if self._closed:
                return not self._degraded and not self._pending
            self._closed = True
        flushed = self.flush()
        self._queue.put(_STOP)
        self._worker.join()
        return flushed

    @property
    def degraded(self) -> bool:
        """返回队列是否出现过最终持久化失败。"""

        with self._lock:
            return self._degraded

    @property
    def pending_messages(self) -> tuple[Message, ...]:
        """返回最终未写入的消息副本。"""

        with self._lock:
            return tuple(self._pending)

    def _run(self) -> None:
        """按队列顺序执行写入和有限重试。"""

        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                self._persist_with_retry(item)
            finally:
                self._queue.task_done()

    def _persist_with_retry(self, item: Message | object) -> None:
        """写入单条消息，失败后保留待写状态。"""

        assert isinstance(item, Message)
        for attempt in range(self._max_retries + 1):
            try:
                self._persist_message(item)
                return
            except Exception:
                if attempt == self._max_retries:
                    with self._lock:
                        self._degraded = True
                        self._pending.append(item)
                    try:
                        self._persist_pending(item)
                    except Exception:
                        pass
