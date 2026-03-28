"""会话管理：内存存储对话历史（MVP 阶段）"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    project: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))
        logger.debug("会话添加用户消息, session={}, 消息长度={}", self.session_id, len(content))

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))
        logger.debug("会话添加助手消息, session={}, 消息长度={}", self.session_id, len(content))

    def get_history(self, max_turns: int = 5) -> list[dict]:
        """返回最近 max_turns 轮对话，格式为 OpenAI messages。"""
        recent = self.messages[-(max_turns * 2) :]
        logger.debug("获取会话历史, session={}, max_turns={}, 返回 {} 条消息", self.session_id, max_turns, len(recent))
        return [{"role": m.role, "content": m.content} for m in recent]


class SessionStore:
    """内存会话存储（MVP）"""

    def __init__(self, max_sessions: int = 1000) -> None:
        self._sessions: dict[str, Session] = {}
        self._max_sessions = max_sessions

    def create(self, project: str) -> Session:
        session_id = uuid.uuid4().hex[:16]
        session = Session(session_id=session_id, project=project)
        self._sessions[session_id] = session
        self._evict_if_needed()
        logger.info("会话创建, session={}, project={}, 当前总数={}", session_id, project, len(self._sessions))
        return session

    def get(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            logger.debug("会话未找到, session={}", session_id)
        return session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        logger.info("会话删除, session={}, 剩余总数={}", session_id, len(self._sessions))

    def _evict_if_needed(self) -> None:
        """超过上限时删除最旧的 session。"""
        if len(self._sessions) > self._max_sessions:
            oldest_id = min(self._sessions, key=lambda k: self._sessions[k].created_at)
            del self._sessions[oldest_id]
            logger.warning("会话淘汰, 超过上限 {}, 淘汰最旧 session={}", self._max_sessions, oldest_id)
