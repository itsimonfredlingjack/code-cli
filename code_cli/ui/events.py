from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

UIEventType = Literal[
    "message", "tool_call", "tool_result", "plan", "status", "diff", "context", "stream_end",
    "agent_state", "verify_result",
]
UIEventSource = Literal["agent", "ui", "system"]


class UIEvent(BaseModel):
    event_id: str
    type: UIEventType
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: str
    payload: dict
    source: UIEventSource
