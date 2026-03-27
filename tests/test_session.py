"""会话管理模块测试"""
from __future__ import annotations

from delphi.retrieval.session import Session, SessionStore


class TestSession:
    """Session 数据类测试"""

    def test_add_user_message(self):
        s = Session(session_id="s1", project="proj")
        s.add_user_message("hello")
        assert len(s.messages) == 1
        assert s.messages[0].role == "user"
        assert s.messages[0].content == "hello"

    def test_add_assistant_message(self):
        s = Session(session_id="s1", project="proj")
        s.add_assistant_message("hi there")
        assert len(s.messages) == 1
        assert s.messages[0].role == "assistant"
        assert s.messages[0].content == "hi there"

    def test_get_history_empty(self):
        s = Session(session_id="s1", project="proj")
        assert s.get_history() == []

    def test_get_history_returns_recent_turns(self):
        s = Session(session_id="s1", project="proj")
        # 添加 4 轮对话（8 条消息）
        for i in range(4):
            s.add_user_message(f"q{i}")
            s.add_assistant_message(f"a{i}")

        # max_turns=2 应返回最近 2 轮（4 条消息）
        history = s.get_history(max_turns=2)
        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "q2"}
        assert history[-1] == {"role": "assistant", "content": "a3"}

    def test_get_history_fewer_than_max(self):
        s = Session(session_id="s1", project="proj")
        s.add_user_message("q0")
        s.add_assistant_message("a0")
        history = s.get_history(max_turns=5)
        assert len(history) == 2

    def test_get_history_format(self):
        s = Session(session_id="s1", project="proj")
        s.add_user_message("question")
        s.add_assistant_message("answer")
        history = s.get_history()
        for msg in history:
            assert "role" in msg
            assert "content" in msg
            assert isinstance(msg["role"], str)
            assert isinstance(msg["content"], str)


class TestSessionStore:
    """SessionStore 测试"""

    def test_create_returns_valid_session(self):
        store = SessionStore()
        session = store.create("my_project")
        assert isinstance(session, Session)
        assert session.project == "my_project"
        assert len(session.session_id) == 16

    def test_get_existing_session(self):
        store = SessionStore()
        created = store.create("proj")
        fetched = store.get(created.session_id)
        assert fetched is created

    def test_get_nonexistent_returns_none(self):
        store = SessionStore()
        assert store.get("nonexistent_id") is None

    def test_delete_session(self):
        store = SessionStore()
        session = store.create("proj")
        store.delete(session.session_id)
        assert store.get(session.session_id) is None

    def test_delete_nonexistent_no_error(self):
        store = SessionStore()
        store.delete("does_not_exist")  # 不应抛异常

    def test_evict_oldest_when_over_max(self):
        store = SessionStore(max_sessions=3)
        sessions = []
        for i in range(4):
            s = store.create(f"proj{i}")
            # 手动设置 created_at 确保顺序明确
            s.created_at = float(i)
            sessions.append(s)

        # 第 4 个 session 创建后触发淘汰，最旧的（created_at=0）应被删除
        assert store.get(sessions[0].session_id) is None
        # 其余 3 个应该还在
        for s in sessions[1:]:
            assert store.get(s.session_id) is not None
