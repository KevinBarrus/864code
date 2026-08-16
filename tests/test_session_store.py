import json
import uuid
from pathlib import Path

import pytest

from core.model import Message
from core.session_store import SessionStore, SessionStoreError


def test_append_creates_session_file_and_directory(tmp_path: Path) -> None:
    """测试第一次追加消息时才创建存储目录和文件。"""

    store = SessionStore(tmp_path)
    session_id = str(uuid.uuid4())

    store.append_message(session_id, Message(role="user", content="你好"))

    session_path = tmp_path / ".864code" / "sessions" / f"{session_id}.jsonl"
    assert session_path.exists()
    assert session_path.parent.is_dir()


def test_jsonl_contains_one_json_record_per_line(tmp_path: Path) -> None:
    """测试多条消息按顺序写成独立的 JSON 记录。"""

    store = SessionStore(tmp_path)
    session_id = str(uuid.uuid4())
    store.append_message(session_id, Message(role="user", content="你好"))
    store.append_message(session_id, Message(role="assistant", content="你好！"))

    path = tmp_path / ".864code" / "sessions" / f"{session_id}.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert records == [
        {"type": "message", "role": "user", "content": "你好"},
        {"type": "message", "role": "assistant", "content": "你好！"},
    ]


def test_load_messages_restores_history_in_order(tmp_path: Path) -> None:
    """测试 JSONL 可以恢复为有序的 Message 列表。"""

    store = SessionStore(tmp_path)
    session_id = str(uuid.uuid4())
    expected = [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！"),
    ]
    for message in expected:
        store.append_message(session_id, message)

    assert store.load_messages(session_id) == expected


def test_missing_session_returns_empty_history(tmp_path: Path) -> None:
    """测试不存在的会话文件返回空历史。"""

    assert SessionStore(tmp_path).load_messages(str(uuid.uuid4())) == []


def test_sessions_are_stored_in_separate_files(tmp_path: Path) -> None:
    """测试不同会话不会共用消息文件。"""

    store = SessionStore(tmp_path)
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())
    store.append_message(first_id, Message(role="user", content="第一会话"))
    store.append_message(second_id, Message(role="user", content="第二会话"))

    assert store.load_messages(first_id) == [
        Message(role="user", content="第一会话")
    ]
    assert store.load_messages(second_id) == [
        Message(role="user", content="第二会话")
    ]


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        ("not-json", "不是有效 JSON"),
        ('{"type":"other"}', "不是消息记录"),
        ('{"type":"message","role":"system","content":"x"}', "角色无效"),
        ('{"type":"message","role":"user","content":1}', "内容无效"),
    ],
)
def test_invalid_records_raise_clear_errors(
    tmp_path: Path,
    content: str,
    expected_message: str,
) -> None:
    """测试损坏或不支持的记录不会被静默忽略。"""

    store = SessionStore(tmp_path)
    session_id = str(uuid.uuid4())
    path = tmp_path / ".864code" / "sessions" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(content + "\n", encoding="utf-8")

    with pytest.raises(SessionStoreError, match=expected_message):
        store.load_messages(session_id)


def test_invalid_session_id_is_rejected(tmp_path: Path) -> None:
    """测试无效 Session ID 不会生成越界文件路径。"""

    store = SessionStore(tmp_path)

    with pytest.raises(SessionStoreError, match="无效的 Session ID"):
        store.load_messages("../../outside")
