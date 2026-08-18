from core.model import Message
from core.session_persistence import SessionPersistenceQueue


def test_persistence_queue_preserves_order_and_retries() -> None:
    persisted: list[str] = []
    attempts = 0

    def persist(message: Message) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("暂时不可写入")
        persisted.append(message.content)

    queue = SessionPersistenceQueue(persist, max_retries=1)
    queue.enqueue(Message(role="user", content="第一条"))
    queue.enqueue(Message(role="assistant", content="第二条"))

    assert queue.flush()
    assert persisted == ["第一条", "第二条"]
    assert not queue.degraded
    assert queue.close()


def test_persistence_queue_marks_degraded_and_keeps_pending_message() -> None:
    def persist(message: Message) -> None:
        raise OSError("持续失败")

    message = Message(role="assistant", content="未写入")
    queue = SessionPersistenceQueue(persist, max_retries=1)
    queue.enqueue(message)

    assert not queue.flush()
    assert queue.degraded
    assert queue.pending_messages == (message,)
    assert not queue.close()
