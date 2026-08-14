"""Session Manager (§25)."""

import time
import uuid
from typing import Dict, Optional
from pydantic import BaseModel, Field


class SessionData(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cookies: Dict[str, str] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    proxy_url: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    request_count: int = 0
    health_score: float = 1.0


class SessionManager:
    """Manages browser and HTTP request sessions (§25)."""

    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}

    def create_session(self, headers: Optional[Dict[str, str]] = None, proxy: Optional[str] = None) -> SessionData:
        sess = SessionData(
            cookies={},
            headers=headers or {},
            proxy_url=proxy
        )
        self._sessions[sess.session_id] = sess
        return sess

    def get_session(self, session_id: str) -> Optional[SessionData]:
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, cookies: Optional[Dict[str, str]] = None, success: bool = True):
        sess = self._sessions.get(session_id)
        if sess:
            sess.request_count += 1
            if cookies:
                sess.cookies.update(cookies)
            if success:
                sess.health_score = min(1.0, sess.health_score + 0.01)
            else:
                sess.health_score = max(0.0, sess.health_score - 0.1)
