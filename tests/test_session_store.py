import json
import os
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


def test_list_sessions_returns_titles_and_recent_first(tmp_path: Path) -> None:
    """测试会话摘要包含标题并按更新时间倒序排列"""

    store = SessionStore(tmp_path)
    older_id = str(uuid.uuid4())
    newer_id = str(uuid.uuid4())
    store.append_message(older_id, Message(role="user", content="旧会话"))
    store.append_message(newer_id, Message(role="user", content="新会话"))

    older_path = tmp_path / ".864code" / "sessions" / f"{older_id}.jsonl"
    newer_path = tmp_path / ".864code" / "sessions" / f"{newer_id}.jsonl"
    older_time = newer_path.stat().st_mtime - 10
    older_path.touch()
    newer_path.touch()
    os.utime(older_path, (older_time, older_time))

    summaries = store.list_sessions()

    assert [summary.session_id for summary in summaries] == [newer_id, older_id]
    assert summaries[0].title == "新会话"
    assert summaries[1].title == "旧会话"
    assert summaries[0].updated_at > summaries[1].updated_at


def test_list_sessions_truncates_title_and_uses_id_for_empty_session(
    tmp_path: Path,
) -> None:
    """测试标题会清理换行并限制长度，空会话使用 Session ID"""

    store = SessionStore(tmp_path)
    long_id = str(uuid.uuid4())
    empty_id = str(uuid.uuid4())
    long_title = "这是一个很长的会话标题\n" + "内容" * 30
    store.append_message(long_id, Message(role="user", content=long_title))
    empty_path = tmp_path / ".864code" / "sessions" / f"{empty_id}.jsonl"
    empty_path.touch()

    summaries = {
        summary.session_id: summary for summary in store.list_sessions()
    }

    assert len(summaries[long_id].title) == 40
    assert "\n" not in summaries[long_id].title
    assert summaries[empty_id].title == empty_id[:8]


def test_list_sessions_rejects_corrupted_file(tmp_path: Path) -> None:
    """测试损坏的会话文件会返回明确错误"""

    store = SessionStore(tmp_path)
    session_id = str(uuid.uuid4())
    path = tmp_path / ".864code" / "sessions" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(SessionStoreError, match=f"无法读取会话 {session_id}"):
        store.list_sessions()
