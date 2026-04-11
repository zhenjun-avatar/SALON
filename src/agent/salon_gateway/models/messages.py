from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WecomTextInbound:
    """企微解密后的文本消息（MVP 只处理 text）。"""

    from_user: str
    to_user: str
    agent_id: str | None
    msg_id: str | None
    content: str
